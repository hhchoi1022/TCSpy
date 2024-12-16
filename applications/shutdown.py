#%%


from threading import Event
import time

from threading import Thread


from tcspy.configuration import mainConfig
from tcspy.devices import SingleTelescope
from tcspy.devices import MultiTelescopes
from tcspy.utils.exception import *

from tcspy.action.level1 import Warm
from tcspy.action.level1 import SlewAltAz
from tcspy.action.level1 import FansOff
from tcspy.action import MultiAction

#%%

class Shutdown(mainConfig):
    
    def __init__(self,
                 MultiTelescopes,
                 abort_action : Event,
                 ):
        super().__init__()
        self.multitelescopes = MultiTelescopes
        self.abort_action = abort_action
        self.is_running = False
    
    def run(self, fanoff = True, slew = True, warm = True):
        startup_thread = Thread(target=self._process, kwargs = dict(fanoff = fanoff, slew = slew, warm = warm))
        startup_thread.start()
    
    def abort(self):
        self.abort_action.set()

    def _process(self, fanoff = True, slew = True, warm = True):
        self.multitelescopes.update_statusfile(status = 'busy', do_trigger = True)
        self.is_running = True
        self.multitelescopes.log.info(f'[{type(self).__name__}] is triggered.')
        
        if fanoff:
            # Focuser fans on
            params_fanson = []
            for telescope_name, telescope in self.multitelescopes.devices.items():
                params_fanson.append(dict())
            
            multi_fanson = MultiAction(array_telescope= self.multitelescopes.devices.values(), array_kwargs= params_fanson, function = FansOff, abort_action = self.abort_action)
            result_multi_fanson = multi_fanson.shared_memory
            
            ## Run
            try:
                multi_fanson.run()
            except AbortionException:
                self.is_running = False
                self.multitelescopes.log.warning(f'[{type(self).__name__}] is aborted.')

            ## Check result
            for tel_name, result in result_multi_fanson.items():
                is_succeeded = result_multi_fanson[tel_name]['succeeded']
                if not is_succeeded:
                    self.multitelescopes.log_dict[tel_name].critical(f'[{type(self).__name__}] is failed: Fans operation failure.')
                    self.multitelescopes.remove(tel_name)        

            ## Check len(devices) > 0
            if len(self.multitelescopes.devices) == 0:
                self.is_running = False
                raise ActionFailedException(f'[{type(self).__name__}] is Failed. Telescopes are not specified')
            
            ## Check abort_action
            if self.abort_action.is_set():
                self.is_running = False
                self.multitelescopes.log.warning(f'[{type(self).__name__}] is aborted.')
                raise AbortionException(f'[{type(self).__name__}] is aborted.')
        
        
        if slew:
            # Telescope slewing
            params_slew = []
            for telescope_name, telescope in self.multitelescopes.devices.items():
                params_slew.append(dict(alt = self.config['SHUTDOWN_ALT'],
                                        az = self.config['SHUTDOWN_AZ']))
            
            multi_slew = MultiAction(array_telescope= self.multitelescopes.devices.values(), array_kwargs= params_slew, function = SlewAltAz, abort_action = self.abort_action)
            result_multi_slew = multi_slew.shared_memory
            
            ## Run
            try:
                multi_slew.run()
            except AbortionException:
                self.is_running = False
                self.multitelescopes.log.warning(f'[{type(self).__name__}] is aborted.')
            
            ## Check result
            for tel_name, result in result_multi_slew.items():
                is_succeeded = result_multi_slew[tel_name]['succeeded']
                if not is_succeeded:
                    self.multitelescopes.log_dict[tel_name].critical(f'[{type(self).__name__}] is failed: Slewing failure.')
                    self.multitelescopes.remove(tel_name)        
        
            ## Check len(devices) > 0
            if len(self.multitelescopes.devices) == 0:
                raise ActionFailedException(f'[{type(self).__name__}] is Failed. Telescopes are not specified')
            
            ## Check abort_action
            if self.abort_action.is_set():
                self.multitelescopes.log.warning(f'[{type(self).__name__}] is aborted.')
                raise AbortionException(f'[{type(self).__name__}] is aborted.')
        if warm:
            # Warm camera
            params_warm = []
            for telescope_name, telescope in self.multitelescopes.devices.items():
                params_warm.append(dict(settemperature = self.config['SHUTDOWN_CCDTEMP'],
                                        tolerance = self.config['SHUTDOWN_CCDTEMP_TOLERANCE']))
            
            multi_warm = MultiAction(array_telescope= self.multitelescopes.devices.values(), array_kwargs= params_warm, function = Warm, abort_action = self.abort_action)
            result_multi_warm = multi_warm.shared_memory
            
            ## Run
            try:
                multi_warm.run()
            except AbortionException:
                self.multitelescopes.log.warning(f'[{type(self).__name__}] is aborted.')
            
            ## Check result
            for tel_name, result in result_multi_warm.items():
                is_succeeded = result_multi_warm[tel_name]['succeeded']
                if not is_succeeded:
                    self.multitelescopes.log_dict[tel_name].critical(f'[{type(self).__name__}] is failed: Warming failure.')
                    self.multitelescopes.remove(tel_name)        
            
            ## Check len(devices) > 0
            if len(self.multitelescopes.devices) == 0:
                self.is_running = False
                raise ActionFailedException(f'[{type(self).__name__}] is Failed. Telescopes are not specified')
            
        self.multitelescopes.log.info(f'[{type(self).__name__}] is finished.')
        self.is_running = False
        self.multitelescopes.update_statusfile(status = 'idle', do_trigger = True)

# %%
if __name__ == '__main__':
    from tcspy.devices import MultiTelescopes
    M = MultiTelescopes()
    Shutdown(M, Event()).run(fanoff =True,
                             slew = True, 
                             warm = True)
# %%
