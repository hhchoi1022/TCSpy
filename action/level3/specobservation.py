#%%
from multiprocessing import Event
import time

from tcspy.devices import SingleTelescope
from tcspy.devices import MultiTelescopes
from tcspy.interfaces import *
from tcspy.utils.target import SingleTarget
from tcspy.utils.exception import *
from tcspy.configuration import mainConfig

from tcspy.action import MultiAction
from tcspy.action.level2 import SingleObservation

class SpecObservation(Interface_Runnable, Interface_Abortable, mainConfig):
    """
    A class representing a spectroscopic observation of multiple telescopes.

    Parameters
    ----------
    MultiTelescopes : MultiTelescopes
        An instance of MultiTelescopes class representing a collection of telescopes to perform the specservation.
    abort_action : Event
        An instance of the built-in Event class to handle the abort action.
    specmode_folder : str
        Path to the folder containing the spectroscopic mode configurations.

    Attributes
    ----------
    multitelescopes : MultiTelescopes
        The MultiTelescopes instance on which the observation has to performed.
    observer : observer
        Details of the observer.
    abort_action : Event
        An instance of Event to handle the abort action.
    _specmode_folder : str
        The Folder containing the config files for the spectroscopic modes.

    Methods
    -------
    run()
        Performs the action to start spectroscopic observation.
    abort()
        A function to abort the ongoing spectroscopic observation process.
    """
    
    def __init__(self, 
                 multitelescopes : MultiTelescopes,
                 abort_action : Event):
        super().__init__()
        self.multitelescopes = multitelescopes
        self.multiaction = None
        self.observer = list(self.multitelescopes.devices.values())[0].observer
        self.abort_action = abort_action
        self.shared_memory = dict()
        self._specmode_folder = self.config['SPECMODE_FOLDER']        
    
    def run(self, 
            exptime : str,
            count : str,
            specmode : str,
            binning : str = '1',
            gain : int = 2750,
            imgtype : str = 'Light',
            ra : float = None,
            dec : float = None,
            alt : float = None,
            az : float = None,
            name : str = None,
            objtype : str = None,
            id_ : str = None,
            force_slewing : bool = False,
            autofocus_use_history : bool = True,
            autofocus_history_duration : float = 60,
            autofocus_before_start : bool = False,
            autofocus_when_filterchange : bool = False,
            autofocus_when_elapsed : bool = False,
            autofocus_elapsed_duration : float = 60,
            observation_status : dict = None,
            ):
        """
        Performs the action to start spectroscopic observation.

        Parameters
        ----------
        exptime : str:
            The exposure time.
        count : str:
            The count of observations.
        specmode : str:
            Spectroscopic mode to be used.
        binning : str (optional):
            Binning value. Default is '1'.
        imgtype : str (optional):
            Type of image. Default is 'Light'.
        ra : float (optional):
            Right Ascension value.
        dec : float (optional):
            Declination value.
        alt : float (optional):
            Altitude value.
        az : float (optional):
            Azimuth value.
        name : str (optional):
            Name of the object.
        objtype : str (optional):
            Type of the object.
        autofocus_before_start : bool (optional):
            If autofocus should be done before start. Default is True.
        autofocus_when_filterchange : bool (optional):
            If autofocus should be done when filter changes. Default is True.
        observation_status : dict (optional):
            if observation_status is specified, resume the observation with this param

        Raises
        ------
        AbortionException
            If the abortion event is triggered during the operation.
        """
        
        """ Test
        exptime= '5,5'
        count= '5,5'
        specmode = 'specall'
        binning= '1,1'
        imgtype = 'Light'
        ra= '300.11667'
        dec= '-20.20556'
        alt = None
        az = None
        name = "COSMOS"
        objtype = 'ToO'
        autofocus_use_history = False
        autofocus_history_duration = 60
        autofocus_before_start= False
        autofocus_when_filterchange= False
        autofocus_when_elapsed = False
        autofocus_elapsed_duration = 60
        observation_status = None
        """
        # Check condition of the instruments for this Action
        self.abort_action.clear()
        status_multitelescope = self.multitelescopes.status
        self.multitelescopes.log.info(f'[{type(self).__name__}] is triggered.')
        for telescope_name, telescope_status in status_multitelescope.items():
            status_filterwheel = telescope_status['filterwheel']
            status_camera = telescope_status['camera']
            status_mount = telescope_status['mount']
            status_focuser = telescope_status['focuser']
            if status_filterwheel.lower() == 'dicconnected':
                self.multitelescopes.log_dict[telescope_name].critical(f'{telescope_name} filterwheel is disconnected.')
            if status_camera.lower() == 'dicconnected':
                self.multitelescopes.log_dict[telescope_name].critical(f'{telescope_name} camera is disconnected.')
            if status_mount.lower() == 'dicconnected':
                self.multitelescopes.log_dict[telescope_name].critical(f'{telescope_name} mount is disconnected.')
            if status_focuser.lower() == 'dicconnected':
                self.multitelescopes.log_dict[telescope_name].critical(f'{telescope_name} focuser is disconnected.')
                
        # Get target instance
        singletarget = SingleTarget(observer = self.observer,
                                    ra = ra, 
                                    dec = dec, 
                                    alt = alt, 
                                    az = az,
                                    name = name,
                                    objtype = objtype,
                                    id_ = id_,
                                    
                                    exptime = exptime,
                                    count = count,
                                    filter_ = None,
                                    binning = binning,
                                    gain = gain,
                                    obsmode = 'Spec',
                                    specmode = specmode)                
        
        # Get filter information
        exposure_params = singletarget.exposure_info
        target_params = singletarget.target_info
        specmode_dict = exposure_params['specmode_filter']
        
        # Define parameters for SingleObservation module for all telescopes
        all_params_obs = dict()
        for tel_name, telescope in self.multitelescopes.devices.items():
            filter_ = specmode_dict[tel_name]
            observation_status_single = None
            if observation_status:
                observation_status_single = observation_status[tel_name]

            params_obs = dict(imgtype= imgtype, 
                              force_slewing = force_slewing,
                              autofocus_use_history = autofocus_use_history,
                              autofocus_history_duration = autofocus_history_duration,
                              autofocus_before_start= autofocus_before_start, 
                              autofocus_when_filterchange= autofocus_when_filterchange, 
                              autofocus_when_elapsed = autofocus_when_elapsed,
                              autofocus_elapsed_time = autofocus_elapsed_duration, 
                              observation_status = observation_status_single,
                              **exposure_params,
                              **target_params)

            params_obs.update(filter_ = filter_)
            all_params_obs[tel_name] = params_obs
        
        # Run Multiple actions
        self.multiaction = MultiAction(array_telescope = self.multitelescopes.devices.values(), array_kwargs = all_params_obs.values(), function = SingleObservation, abort_action  = self.abort_action)
        self.shared_memory = self.multiaction.shared_memory
        try:
            self.multiaction.run()
        except AbortionException:
            self.multitelescopes.log.warning(f'[{type(self).__name__}] is aborted.')
            raise AbortionException(f'[{type(self).__name__}] is aborted.')
        
        is_all_succeeded = []
        for tel_name, result in self.shared_memory.items():
            is_succeeded = self.shared_memory[tel_name]['succeeded']
            is_all_succeeded.append(is_succeeded)
            if is_succeeded:
                self.multitelescopes.log_dict[tel_name].info(f'[{type(self).__name__}] is finished')
            else:
                self.multitelescopes.log_dict[tel_name].info(f'[{type(self).__name__}] is failed')
        return all(is_all_succeeded)

    def abort(self):
        """
        A function to abort the ongoing spectroscopic observation process.
        """
        #self.multiaction.abort()
        self.abort_action.set()
    
# %%
if __name__ == '__main__':
    import time
    from tcspy.devices import SingleTelescope
    start = time.time()
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
    
    print(time.time() - start)

    start = time.time()

    M = MultiTelescopes(list_telescopes)
#%%
if __name__ == '__main__':
    #M = MultiTelescopes([SingleTelescope(21)])

    abort_action = Event()
    S  = SpecObservation(M, abort_action)
    exptime= '10'
    count= '2,2'
    specmode = 'specall'
    binning= '1,1'
    imgtype = 'Light'
    ra= None
    dec= None
    alt =40 
    az = 300
    name = "GRB240516A"
    objtype = 'ToO'
    autofocus_before_start= False
    autofocus_when_filterchange= False
    autofocus_when_elapsed = False
    kwargs = dict(exptime = exptime, count = count, specmode = specmode,
        binning = binning, imgtype = imgtype, ra = ra, dec = dec,
        alt = alt, az = az, name = name, objtype = objtype,
        autofocus_before_start= autofocus_before_start,
        autofocus_when_filterchange= autofocus_when_filterchange,
        autofocus_when_elapsed = autofocus_when_elapsed,
        )
    from threading import Thread
    t = Thread(target = S.run, kwargs= kwargs)
    t.start()
    #t.abort()
# %%
if __name__ == '__main__':
    S.run(exptime = exptime, count = count, specmode = specmode,
        binning = binning, imgtype = imgtype, ra = ra, dec = dec,
        alt = alt, az = az, name = name, objtype = objtype,
        autofocus_before_start= autofocus_before_start,
        autofocus_when_filterchange= autofocus_when_filterchange,
        observation_status= S.observation_status)
# %%
