#%%
from astropy.time import Time
import astropy.units as u
from multiprocessing import Event, Lock
from threading import Thread
import time
import uuid
from tcspy.action.level1 import *
from tcspy.action.level2 import *
from tcspy.action.level3 import *
from tcspy.configuration import mainConfig
from tcspy.devices import MultiTelescopes
from tcspy.devices import SingleTelescope
from tcspy.utils.databases import DB
from tcspy.devices.weather import WeatherUpdater
from tcspy.devices.safetymonitor import SafetyMonitorUpdater
from tcspy.utils.error import *
from tcspy.utils.target import SingleTarget
from tcspy.utils.exception import *
#%%


class NightObservation(mainConfig):
    
    def __init__(self, 
                 MultiTelescopes : MultiTelescopes,
                 abort_action : Event,
                 ):
        super().__init__()
        self.multitelescopes = MultiTelescopes
        self.abort_action = abort_action
        self.is_running = False
        self._DB = None
        self.weathersafety = True # For test
        self.autofocus = self._default_autofocus_config()
        self._weather = next(iter(self.multitelescopes.devices.values())).devices['weather']
        self._safetymonitor = next(iter(self.multitelescopes.devices.values())).devices['safetymonitor']
        if self.config['NIGHTOBS_SAFETYPE'].upper() == 'WEATHER':
            self._is_safe = self._is_weather_safe
        else:
            self._is_safe = self._is_safetymonitor_safe
        self._weather_updater = None
        self._obsnight = None
        self.action_queue = list()
        self.tel_queue = dict()
        self.tel_lock = Lock()
        self.action_lock = Lock()
        self.is_ToO_triggered = False
        self.is_obs_triggered = False
        self._ToO_abort = Event()
        self._observation_abort = Event()
        self.initialize()
    
    def _default_autofocus_config(self):
        class default_autofocus: 
            def __init__(self):
                self.use_history = True
                self.history_duration = 60 
                self.before_start = True
                self.when_filterchange = True
                self.when_elapsed = True
                self.elapsed_duration = 60
            def __repr__(self):
                return ('AUTOFOCUS CONFIGURATION ============\n'
                        f'autofocus.use_history = {self.use_history}\n'
                        f'autofocus.history_duration = {self.history_duration}\n'
                        f'autofocus.before_start = {self.before_start}\n'
                        f'autofocus.when_filterchange = {self.when_filterchange}\n' 
                        f'autofocus.when_elapsed = {self.when_elapsed}\n'
                        f'autofocus.elapsed_duration = {self.elapsed_duration}\n'
                        '=====================================')
        return default_autofocus()
        
    def initialize(self):
        
        # Initialize Daily target table 
        self._DB = DB(utctime = Time.now()).Daily
        self._DB.initialize(initialize_all= True)
        is_connected_DB = self._DB.connected
        
        if not is_connected_DB:
            raise DBConnectionError('DB cannot be connected. Check MySQL server')
        
        # Connect Weather Updater
        self._weather_updater = WeatherUpdater()
        Thread(target = self._weather_updater.run, kwargs = dict(abort_action = self.abort_action), daemon = False).start()
        # Connect SafetyMonitor Updater
        self._safemonitor_updater = SafetyMonitorUpdater()
        Thread(target = self._safemonitor_updater.run, kwargs = dict(abort_action = self.abort_action), daemon = False).start()
        # Get status of all telescopes
        status_devices = self.multitelescopes.status
        for tel_name, status in status_devices.items():
            if self._is_tel_ready(status):
                self.tel_queue[tel_name] = self.multitelescopes.devices[tel_name]
        
        # Set observing night
        self._obsnight = self._DB.obsnight
        
        # Initialization is finished

    def _is_tel_ready(self, tel_status_dict):
        ready_tel = tel_status_dict['mount'].upper() == 'IDLE'
        ready_cam = tel_status_dict['camera'].upper() == 'IDLE'
        ready_filt = tel_status_dict['filterwheel'].upper() == 'IDLE'
        ready_focus = tel_status_dict['focuser'].upper() == 'IDLE'
        return all([ready_tel, ready_cam, ready_filt, ready_focus])
    
    def _is_weather_safe(self):
        weather_status = self._weather.get_status()
        if weather_status['is_safe'] == True:
            return True
        else:
            return False

    def _is_safetymonitor_safe(self):
        safetymonitor_status = self._safetymonitor.get_status()
        if safetymonitor_status['is_safe'] == True:
            return True
        else:
            return False
    
    def _specobs(self, target, telescopes, abort_action, observation_status):
        kwargs = dict(exptime = target['exptime'], 
                    count = target['count'],
                    specmode = target['specmode'],
                    binning = target['binning'], 
                    gain = target['gain'],
                    imgtype = 'Light', 
                    ra = target['RA'],
                    dec = target['De'], 
                    name = target['objname'],
                    objtype = target['objtype'], 
                    id_ = target['id'],
                    note = target['note'],
                    autofocus_use_history = self.autofocus.use_history,
                    autofocus_history_duration = self.autofocus.history_duration,
                    autofocus_before_start = self.autofocus.before_start,
                    autofocus_when_filterchange = self.autofocus.when_filterchange,
                    autofocus_when_elapsed = self.autofocus.when_elapsed,
                    autofocus_elapsed_duration = self.autofocus.elapsed_duration,
                    observation_status = observation_status)  
        
        self.is_obs_triggered = True
        self._DB.update_target(update_value = 'scheduled', update_key = 'status', id_value = target['id'], id_key = 'id')
        action = SpecObservation(multitelescopes= telescopes, abort_action = abort_action)
        action_id = uuid.uuid4().hex
        # Pop the telescope from the tel_queue
        self._pop_telescope(telescope = telescopes)
        # Apped the action and telescope to the action_queue
        self._put_action(target = target, action = action, telescopes = telescopes, action_id = action_id)
        
        # Run observation
        result_action = action.run(**kwargs)
        
        # Update the target status
        if result_action:
            self._DB.update_target(update_value = 'observed', update_key = 'status', id_value = target['id'], id_key = 'id')
        else:
            self._DB.update_target(update_value = 'failed', update_key = 'status', id_value = target['id'], id_key = 'id')
        # Pop the action and telescope from  the action_queue
        self._pop_action(action_id = action_id)
        # Apped the telescope to the tel_queue
        self._put_telescope(telescope = telescopes)
        
    def _deepobs(self, target, telescopes, abort_action, observation_status):
        kwargs = dict(exptime = target['exptime'], 
                    count = target['count'],
                    filter_ = target['filter_'],
                    binning = target['binning'], 
                    gain = target['gain'],
                    imgtype = 'Light',
                    ra = target['RA'],
                    dec = target['De'], 
                    name = target['objname'],
                    objtype = target['objtype'], 
                    id_ = target['id'],
                    note = target['note'],
                    autofocus_use_history = self.autofocus.use_history,
                    autofocus_history_duration = self.autofocus.history_duration,
                    autofocus_before_start = self.autofocus.before_start,
                    autofocus_when_filterchange = self.autofocus.when_filterchange,
                    autofocus_when_elapsed = self.autofocus.when_elapsed,
                    autofocus_elapsed_duration = self.autofocus.elapsed_duration,
                    observation_status = observation_status)  

        self._DB.update_target(update_value = 'scheduled', update_key = 'status', id_value = target['id'], id_key = 'id')
        action = DeepObservation(multitelescopes= telescopes, abort_action = abort_action)
        action_id = uuid.uuid4().hex
        # Pop the telescope from the tel_queue
        self._pop_telescope(telescope = telescopes)
        # Apped the action and telescope to the action_queue
        self._put_action(target = target, action = action, telescopes = telescopes, action_id = action_id)
        
        # Run observation
        result_action = action.run(**kwargs)
        
        # Update the target status
        if result_action:
            self._DB.update_target(update_value = 'observed', update_key = 'status', id_value = target['id'], id_key = 'id')
        else:
            self._DB.update_target(update_value = 'failed', update_key = 'status', id_value = target['id'], id_key = 'id')
        # Pop the action and telescope from the action_queue
        self._pop_action(action_id = action_id)
        # Apped the telescope to the tel_queue
        self._put_telescope(telescope = telescopes)
        
    def _searchobs(self, target, telescopes, abort_action, observation_status):
        kwargs = dict(exptime = target['exptime'], 
                    count = target['count'],
                    filter_ = target['filter_'],
                    binning = target['binning'], 
                    gain = target['gain'],
                    imgtype = 'Light', 
                    ra = target['RA'],
                    dec = target['De'], 
                    name = target['objname'],
                    obsmode = 'Search',
                    objtype = target['objtype'],
                    id_ = target['id'],
                    note = target['note'],
                    ntelescope = 1,
                    autofocus_use_history = self.autofocus.use_history,
                    autofocus_history_duration = self.autofocus.history_duration,
                    autofocus_before_start = self.autofocus.before_start,
                    autofocus_when_filterchange = self.autofocus.when_filterchange,
                    autofocus_when_elapsed = self.autofocus.when_elapsed,
                    autofocus_elapsed_duration = self.autofocus.elapsed_duration,
                    observation_status = observation_status)    

        self._DB.update_target(update_value = 'scheduled', update_key = 'status', id_value = target['id'], id_key = 'id')
        action = SingleObservation(singletelescope= telescopes, abort_action = abort_action)
        action_id = uuid.uuid4().hex
        # Pop the telescope from the tel_queue
        self._pop_telescope(telescope = telescopes)
        # Appedd the action and telescope to the action_queue
        self._put_action(target = target, action = action, telescopes = telescopes, action_id = action_id)
        
        # Run observation
        result_action = action.run(**kwargs)
        
        # Update the target status
        if result_action:
            self._DB.update_target(update_value = 'observed', update_key = 'status', id_value = target['id'], id_key = 'id')
        else:
            self._DB.update_target(update_value = 'failed', update_key = 'status', id_value = target['id'], id_key = 'id')
        # Pop the action and telescope from the action_queue
        self._pop_action(action_id = action_id)
        # Apped the telescope to the tel_queue
        self._put_telescope(telescope = telescopes)

    def _singleobs(self, target, telescopes, abort_action, observation_status):
        kwargs = dict(exptime=target['exptime'], 
                    count = target['count'],
                    filter_ = target['filter_'],
                    binning = target['binning'], 
                    gain = target['gain'],
                    imgtype = 'Light', 
                    ra = target['RA'],
                    dec = target['De'], 
                    name = target['objname'],
                    obsmode = 'Single',
                    objtype = target['objtype'],
                    id_ = target['id'],
                    note = target['note'],
                    ntelescope = 1,
                    autofocus_use_history = self.autofocus.use_history,
                    autofocus_history_duration = self.autofocus.history_duration,
                    autofocus_before_start = self.autofocus.before_start,
                    autofocus_when_filterchange = self.autofocus.when_filterchange,
                    autofocus_when_elapsed = self.autofocus.when_elapsed,
                    autofocus_elapsed_duration = self.autofocus.elapsed_duration,
                    observation_status = observation_status)          
        
        self._DB.update_target(update_value = 'scheduled', update_key = 'status', id_value = target['id'], id_key = 'id')
        action = SingleObservation(singletelescope= telescopes, abort_action = abort_action)
        action_id = uuid.uuid4().hex
        # Pop the telescope from the tel_queue
        self._pop_telescope(telescope = telescopes)
        # Appedd the action and telescope to the action_queue
        self._put_action(target = target, action = action, telescopes = telescopes, action_id = action_id)
        
        # Run observation
        result_action = action.run(**kwargs)
        
        # Update the target status
        if result_action:
            self._DB.update_target(update_value = 'observed', update_key = 'status', id_value = target['id'], id_key = 'id')
        else:
            self._DB.update_target(update_value = 'failed', update_key = 'status', id_value = target['id'], id_key = 'id')
        # Pop the action and telescope from the action_queue
        self._pop_action(action_id = action_id)
        # Apped the telescope to the tel_queue
        self._put_telescope(telescope = telescopes)
    
    def _obstrigger(self, target, abort_action, observation_status = None):     
        obsmode = target['obsmode'].upper()
        if obsmode == 'SPEC':
            if set(self.multitelescopes.devices.keys()) == set(self.tel_queue.keys()): ####################################################
                telescopes = MultiTelescopes(SingleTelescope_list = list(self.tel_queue.values()))
                thread = Thread(target= self._specobs, kwargs = {'telescopes':telescopes, 'target': target, 'abort_action': abort_action, 'observation_status': observation_status}, daemon = False)
                thread.start()
        elif obsmode == 'DEEP':
            ntelescope = target['ntelescope']
            if len(self.tel_queue) >= ntelescope:
                telescopes = MultiTelescopes(SingleTelescope_list = [self.tel_queue.popitem()[1] for i in range(ntelescope)])
                thread = Thread(target= self._deepobs, kwargs = {'telescopes':telescopes, 'target': target, 'abort_action': abort_action, 'observation_status': observation_status}, daemon = False)
                thread.start()
        elif obsmode == 'SEARCH':
            if len(self.tel_queue) >= 1:
                tel_name, telescopes = self.tel_queue.popitem()
                thread = Thread(target= self._searchobs, kwargs = {'telescopes':telescopes, 'target': target, 'abort_action': abort_action, 'observation_status': observation_status}, daemon = False)
                thread.start()
        else:
            if len(self.tel_queue) >= 1:
                tel_name, telescopes = self.tel_queue.popitem()
                thread = Thread(target= self._singleobs, kwargs = {'telescopes':telescopes, 'target': target, 'abort_action': abort_action, 'observation_status': observation_status}, daemon = False)
                thread.start()   
        return True 
    
    def _obsresume(self, target, telescopes, abort_action, observation_status = None):
        # Check observability
        singletarget = SingleTarget(observer = self.multitelescopes.observer, 
                                    ra = target['RA'], dec = target['De'], 
                                    exptime = target['exptime'], count = target['count'], filter_ = target['filter_'], binning = target['binning'], specmode = target['specmode'])
        is_observable = singletarget.is_observable(utctime= Time.now() + singletarget.exposure_info['exptime_tot'] * u.s)
        obsmode = target['obsmode'].upper()        
        
        if is_observable:
            if obsmode == 'SPEC':
                if set(self.multitelescopes.devices.keys()) == set(self.tel_queue.keys()): ####################################################
                    thread = Thread(target= self._specobs, kwargs = {'telescopes':telescopes, 'target': target, 'abort_action': abort_action, 'observation_status': observation_status}, daemon = False)
                    thread.start()
            elif obsmode == 'DEEP':
                ntelescope = target['ntelescope']
                if len(self.tel_queue) >= ntelescope:
                    thread = Thread(target= self._deepobs, kwargs = {'telescopes':telescopes, 'target': target, 'abort_action': abort_action, 'observation_status': observation_status}, daemon = False)
                    thread.start()
            elif obsmode == 'SEARCH':
                ntelescope = target['ntelescope']
                if len(self.tel_queue) >= 1:
                    thread = Thread(target= self._searchobs, kwargs = {'telescopes':telescopes, 'target': target, 'abort_action': abort_action, 'observation_status': observation_status}, daemon = False)
                    thread.start()
            else:
                if len(self.tel_queue) >= 1:
                    thread = Thread(target= self._singleobs, kwargs = {'telescopes':telescopes, 'target': target, 'abort_action': abort_action, 'observation_status': observation_status}, daemon = False)
                    thread.start()
        else:
            self.multitelescopes.log.warning('Observation cannot be resumed: Target is unobservable')
        return True
    
    def _ToOobservation(self):
        self.is_ToO_triggered = True
        aborted_action = self.abort_observation()
        self.multitelescopes.log.info('ToO is triggered.================================')
        obs_start_time = self._obsnight.sunset_astro
        obs_end_time = self._obsnight.sunrise_astro
        now = Time.now()
        
        # Wait until sunset
        while now < obs_start_time:
            time.sleep(5)
            print(f'Wait until sunset... [sunset = {obs_start_time.isot}]')
            now = Time.now()
            if self.abort_action.is_set():
                self.multitelescopes.log.warning(f'[{type(self).__name__}] is aborted.')
                raise AbortionException(f'[{type(self).__name__}] is aborted.')
                
        
        # Trigger observation until sunrise
        while now < obs_end_time:
            if self.abort_action.is_set():
                self.multitelescopes.log.warning(f'[{type(self).__name__}] is aborted.')
                raise AbortionException(f'[{type(self).__name__}] is aborted.')
            now = Time.now()
            
            # Initialize the Daily target tbl
            self._DB.initialize(initialize_all = False)
            time.sleep(0.5)  
            
            # Retrieve best target
            best_target, score = self._DB.best_target(utctime = now)
            print(f'Best target: {best_target}')
            
            # Check weather status
            is_weather_safe = self._is_safe()
            aborted_action_ToO = None
            
            # If weather is safe
            if is_weather_safe:      
                # If there is any aborted_action due to unsafe weather, resume the observation
                if aborted_action_ToO:
                    for action in aborted_action_ToO:
                        time.sleep(0.5)
                        if set(action['telescope'].devices.keys()).issubset(self.tel_queue.keys()):
                            if isinstance(action['action'], (SpecObservation, DeepObservation)):
                                observation_status = {tel_name: status['status'] for tel_name, status in action['action'].shared_memory.items()}
                            else:
                                observation_status =  action['action'].shared_memory['status']
                            self._obsresume(target = action['target'], telescopes = action['telescope'], abort_action = self._observation_abort, observation_status = observation_status)
                    aborted_action_ToO = None
                # If there is no observable target
                if not best_target:
                    break
                
                if not self.is_ToO_triggered:
                    break
                else:
                    objtype = best_target['objtype'].upper()
                    # If target is not ToO
                    if not objtype == 'TOO':
                        break
                    # Else; trigger observation
                    else:
                        self._obstrigger(target = best_target, abort_action = self._ToO_abort)
            # If weather is unsafe
            else:
                aborted_action_ToO = self.abort_ToO()
            time.sleep(0.5)
        while len(self.action_queue) > 0:
            print('Waiting for ToO to be finished')
            time.sleep(1)
        self.is_ToO_triggered = False
        self._observation_abort = Event()
        
        for action in aborted_action:
            time.sleep(0.5)
            if set(action['telescope'].devices.keys()).issubset(self.tel_queue.keys()):
                if isinstance(action['action'], (SpecObservation, DeepObservation)):
                    observation_status = {tel_name: status['status'] for tel_name, status in action['action'].shared_memory.items()}
                else:
                    observation_status =  action['action'].shared_memory['status']
                self._obsresume(target = action['target'], telescopes = action['telescope'], abort_action = self._observation_abort, observation_status = observation_status)
        return True
    
    def run(self):
        if not self.is_running:
            Thread(target = self._process).start()
        else:
            self.multitelescopes.log.critical(f'[{type(self).__name__}] cannot be run twice.')
            
    def _process(self):
        self.multitelescopes.log.info(f'[{type(self).__name__}] is triggered.')
        self.is_running = True
        self._observation_abort = Event()
        self._ToO_abort = Event()
        obs_start_time = self._obsnight.sunset_astro
        obs_end_time = self._obsnight.sunrise_astro
        now = Time.now() 
        
        # Wait until sunset
        if now < obs_start_time:
            self.multitelescopes.log.info('Wait until sunset... [%.2f hours left]'%((Time.now() - obs_start_time)*24).value)
            print('Wait until sunset... [%.2f hours left]'%((Time.now() - obs_start_time)*24).value)
        while now < obs_start_time:
            time.sleep(5)
            now = Time.now()
            if self.abort_action.is_set():
                self.multitelescopes.log.warning(f'[{type(self).__name__}] is aborted.')
                raise AbortionException(f'[{type(self).__name__}] is aborted.')
        
        aborted_action = None
        # Trigger observation until sunrise
        while now < obs_end_time:
            if self.abort_action.is_set():
                self.multitelescopes.log.warning(f'[{type(self).__name__}] is aborted.')
                raise AbortionException(f'[{type(self).__name__}] is aborted.')
            now = Time.now() 
            
            # Initialize the Daily target tbl
            self._DB.initialize(initialize_all = False)
            time.sleep(0.5)  
            
            # Retrieve best target
            best_target, score = self._DB.best_target(utctime = now)
            print(f'Best target: {best_target}')
            
            # Check weather status
            is_weather_safe = self._is_safe()
            
            # If weather is safe
            if is_weather_safe:
                # If there is any aborted_action due to unsafe weather, resume the observation
                if aborted_action:
                    for action in aborted_action:
                        time.sleep(0.5)
                        if set(action['telescope'].devices.keys()).issubset(self.tel_queue.keys()):
                            if isinstance(action['action'], (SpecObservation, DeepObservation)):
                                observation_status = {tel_name: status['status'] for tel_name, status in action['action'].shared_memory.items()}
                            else:
                                observation_status =  action['action'].shared_memory['status']
                            action_tried = self._obsresume(target = action['target'], telescopes = action['telescope'], abort_action = self._observation_abort, observation_status = observation_status)
                    aborted_action = None
                else:
                    if best_target:
                        objtype = best_target['objtype'].upper()
                        if objtype == 'TOO':
                            self._ToOobservation()
                        else:
                            self._obstrigger(target = best_target, abort_action = self._observation_abort)
                    else:
                        print('No observable target exists... Waiting for target being observable or new target input')
            # If weather is unsafe
            else:
                aborted_action = self.abort_observation()
            time.sleep(0.5)
        self.is_running = False
        print('observation finished', Time.now())
        
    def _put_action(self, target, action, telescopes, action_id):
        # Acquire the lock before putting action into the action queue
        self.action_lock.acquire()
        try:
            # Put action and corresponding telescopes into the action queue
            self.action_queue.append({'target': target, 'action': action, 'telescope' : telescopes, 'id' : action_id})
        finally:
            # Release the lock
            self.action_lock.release()
            
    def _pop_action(self, action_id):
        # Acquire the lock before putting action into the action queue
        self.action_lock.acquire()
        try:
            # Put action and corresponding telescopes into the action queue
            self.action_queue = [item for item in self.action_queue if item.get('id') != action_id]
        finally:
            # Release the lock
            self.action_lock.release()
            
    def _put_telescope(self, telescope):
        # Acquire the lock before modifying self.used_telescopes
        self.tel_lock.acquire()
        try:
            # Append telescopes used in the action to the list
            if isinstance(telescope, SingleTelescope):
                self.tel_queue[telescope.tel_name] = telescope
            if isinstance(telescope, MultiTelescopes):
                for tel_name, tel in telescope.devices.items():
                    self.tel_queue[tel_name] = tel
        finally:
            # Release the lock
            self.tel_lock.release()
            
    def _pop_telescope(self, telescope):
        # Acquire the lock before modifying self.used_telescopes
        self.tel_lock.acquire()
        try:
            # Append telescopes used in the action to the list
            if isinstance(telescope, SingleTelescope):
                self.tel_queue.pop(telescope.tel_name, None)
            if isinstance(telescope, MultiTelescopes):
                for tel_name, tel in telescope.devices.items():
                    self.tel_queue.pop(tel_name, None)
        finally:
            # Release the lock
            self.tel_lock.release()
    
    def abort(self):
        # Abort NightObservation
        self.abort_action.set()
        obs_history = None
        if self.is_ToO_triggered:
            obs_history = self.abort_ToO()
        else:
            obs_history = self.abort_observation()
        self.is_running = False
        return obs_history    
    
    def abort_observation(self):
        # Abort ordinary observation
        action_history = self.action_queue
        self._observation_abort.set()
        if len(action_history) > 0:
            for action in action_history:
                action['telescope'].log.warning('Waiting for ordinary observation aborted...')
                # Check process aborted
                while any(action['action'].multiaction.status.values()):
                    time.sleep(0.2)
                # Check telescope ready to observe
                #all_tel_status = {tel_name:self._is_tel_ready(tel_status) for tel_name, tel_status in action['telescope'].status.items()}
                #while not all(all_tel_status.values()):
                #    all_tel_status = {tel_name:self._is_tel_ready(tel_status) for tel_name, tel_status in action['telescope'].status.items()}
                self._pop_action(action_id =action['id'])
                self._put_telescope(telescope = action['telescope'])
                self._DB.update_target(update_value = 'aborted', update_key = 'status', id_value = action['target']['id'], id_key = 'id')

        self.is_obs_triggered = False
        # Get status of all telescopes

        self._observation_abort = Event()
        return action_history
        
    def abort_ToO(self, retract_targets : bool = False):
        # Abort ToO observation
        action_history = self.action_queue
        self._ToO_abort.set()
        if retract_targets:
            targets = self._DB.data
            ToO_targets_unobserved = targets[targets['objtype'].upper() == 'TOO']
            if len(ToO_targets_unobserved) > 0:
                for ToO_target in ToO_targets_unobserved:
                    self._DB.update_target(update_value = 'retracted', update_key = 'status', id_value =  ToO_target['id'], id_key = 'id')
        if len(action_history) > 0:
            for action in action_history:
                self.multitelescopes.log.warning('Waiting for ordinary observation aborted...')
                while any(action['action'].multiaction.status.values()):
                    time.sleep(0.2)
                self._pop_action(action_id =action['id'])
                self._put_telescope(telescope = action['telescope'])   
                self._DB.update_target(update_value = 'aborted', update_key = 'status', id_value = action['target']['id'], id_key = 'id')    
        self.is_ToO_triggered = False
        self._ToO_abort = Event()
        return action_history

    def observation_status(self):
        for action in self.action_queue:
            for shared_memory in action['action'].shared_memory.values():
                print(dict(shared_memory))

# %%
if __name__ == '__main__':
    list_telescopes = [SingleTelescope(1),
                         SingleTelescope(2),
                         SingleTelescope(3),
                         SingleTelescope(5),
                         SingleTelescope(6),
                         SingleTelescope(7),
                         SingleTelescope(8),
                         SingleTelescope(9),
                         SingleTelescope(10),
                         SingleTelescope(11),
                         ]
#%%
if __name__ == '__main__':
    M = MultiTelescopes(list_telescopes)
    abort_action = Event()
    #Startup(multitelescopes= M , abort_action= abort_action).run()
    R = NightObservation(M, abort_action= abort_action)
    #Thread(target= R.observation).start()
    #R.run()
# %%
