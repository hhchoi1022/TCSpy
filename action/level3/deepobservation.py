#%%
from multiprocessing import Event
import time

from tcspy.devices import SingleTelescope
from tcspy.devices import MultiTelescopes
from tcspy.interfaces import *
from tcspy.utils.target import SingleTarget
from tcspy.utils.exception import *

from tcspy.action import MultiAction
from tcspy.action.level2 import SingleObservation

#%%
class DeepObservation(Interface_Runnable, Interface_Abortable):
    """
    A class representing a deep observation of multiple telescopes.

    Parameters
    ----------
    MultiTelescopes : MultiTelescopes
        An instance of MultiTelescopes class representing a collection of telescopes to perform the deep observation.
    abort_action : Event
        An instance of the built-in Event class to handle the abort action.

    Attributes
    ----------
    multitelescopes : MultiTelescopes
        The MultiTelescopes instance on which the observation has to performed.
    observer : observer
        Details of the observer.
    abort_action : Event
        An instance of Event to handle the abort action.
    _log : _log
        Logging the details of the operation.

    Methods
    -------
    run()
        Performs the action to start deep observation.
    abort()
        A function to abort the ongoing deep observation process.
    """
    
    def __init__(self, 
                 multitelescopes : MultiTelescopes,
                 abort_action : Event):        
        self.multitelescopes = multitelescopes
        self.observer = list(self.multitelescopes.devices.values())[0].observer
        self.abort_action = abort_action
        self.shared_memory = dict()
        self._log = multitelescopes.log
    
    def _format_params(self,
                       imgtype : str = 'Light',
                       autofocus_before_start = True,
                       autofocus_when_filterchange = True,
                       **kwargs):
        format_kwargs = dict()
        format_kwargs['imgtype'] = imgtype
        format_kwargs['autofocus_before_start'] = autofocus_before_start
        format_kwargs['autofocus_when_filterchange'] = autofocus_when_filterchange

        # Other information
        for key, value in kwargs.items():
            format_kwargs[key] = value
        return format_kwargs
    
    def run(self, 
            exptime : str,
            count : str,
            filter_ : str,
            binning : str = '1',
            imgtype : str = 'Light',
            ra : float = None,
            dec : float = None,
            alt : float = None,
            az : float = None,
            name : str = None,
            objtype : str = None,
            autofocus_before_start : bool = True,
            autofocus_when_filterchange : bool = True,
            observation_status : dict = None
            ):
        """
        Performs the action to start deep observation.

        Parameters
        ----------
        exptime : str:
            The exposure time.
        count : str:
            The count of observations.
        filter_ : str:
            Filter to be used.
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
        exptime= '10,10'
        count= '5,5'
        filter_ = 'g,r'
        binning= '1,1'
        imgtype = 'Light'
        ra= '200.4440'
        dec= '-20.5520'
        alt = None
        az = None
        name = "NGC3147"
        objtype = 'ToO'
        autofocus_before_start= True
        autofocus_when_filterchange= True
        observation_status = None

        """
        
        # Check condition of the instruments for this Action
        status_multitelescope = self.multitelescopes.status
        for telescope_name, telescope_status in status_multitelescope.items():
            self._log[telescope_name].info(f'[{type(self).__name__}] is triggered.')
            status_filterwheel = telescope_status['filterwheel']
            status_camera = telescope_status['camera']
            status_mount = telescope_status['mount']
            status_focuser = telescope_status['focuser']
            if status_filterwheel.lower() == 'dicconnected':
                self._log[telescope_name].critical(f'{telescope_name} filterwheel is disconnected.')
            if status_camera.lower() == 'dicconnected':
                self._log[telescope_name].critical(f'{telescope_name} camera is disconnected.')
            if status_mount.lower() == 'dicconnected':
                self._log[telescope_name].critical(f'{telescope_name} mount is disconnected.')
            if status_focuser.lower() == 'dicconnected':
                self._log[telescope_name].critical(f'{telescope_name} focuser is disconnected.')

        ntelescope = len(self.multitelescopes.devices)
        # Get target instance
        singletarget = SingleTarget(observer = self.observer,
                                    ra = ra, 
                                    dec = dec, 
                                    alt = alt, 
                                    az = az,
                                    name = name,
                                    objtype = objtype,
                                    
                                    exptime = exptime,
                                    count = count,
                                    filter_ = filter_,
                                    binning = binning,
                                    obsmode = 'Deep',
                                    ntelescope= ntelescope)                
        
        # Get filter information
        exposure_params = singletarget.exposure_info
        target_params = singletarget.target_info
        
        # Define parameters for SingleObservation module for all telescopes
        all_params_obs = dict()
        for tel_name, telescope in self.multitelescopes.devices.items():
            observation_status_single = None
            if observation_status:
                observation_status_single = observation_status[tel_name]
                
            params_obs = self._format_params(imgtype= imgtype, 
                                             autofocus_before_start= autofocus_before_start, 
                                             autofocus_when_filterchange= autofocus_when_filterchange, 
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
            for tel_name in  self.multitelescopes.devices.keys():
                self._log[tel_name].warning(f'[{type(self).__name__}] is aborted.')
        
        for tel_name, result in self.shared_memory.items():
            is_succeeded = self.shared_memory[tel_name]
            if is_succeeded:
                self._log[tel_name].info(f'[{type(self).__name__}] is finished')
            else:
                self._log[tel_name].info(f'[{type(self).__name__}] is failed')
                
    def abort(self):
        """
        A function to abort the ongoing spectroscopic observation process.
        """
        #self.multiaction.abort()
        self.abort_action.set()

     
# %%
if __name__ == '__main__':
    telescope_1 = SingleTelescope(21)
    telescope_10 = SingleTelescope(10)
    telescope_11 = SingleTelescope(11)
    M = MultiTelescopes([telescope_1])#, telescope_10, telescope_11])
    abort_action = Event()
    S  = DeepObservation(M, abort_action)
    exptime= '60,60'
    count= '1,1'
    filter_ = 'g,r'
    binning= '2,2'
    imgtype = 'Light'
    ra= '150.11667'
    dec= '2.20556'
    alt = None
    az = None
    name = "COSMOS"
    objtype = 'Commissioning'
    autofocus_before_start= True
    autofocus_when_filterchange= True
    S.run(exptime = exptime, count = count, filter_ = filter_,
        binning = binning, imgtype = imgtype, ra = ra, dec = dec,
        alt = alt, az = az, name = name, objtype = objtype,
        autofocus_before_start= autofocus_before_start,
        autofocus_when_filterchange= autofocus_when_filterchange)
    S.abort()
    # %%
