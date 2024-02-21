#%%
from threading import Event
from astropy.table import Table

from tcspy.devices import IntegratedDevice
from tcspy.devices import DeviceStatus
from tcspy.interfaces import *
from tcspy.utils.error import *
from tcspy.utils.logger import mainLogger
from tcspy.utils.target import mainTarget
from tcspy.action.level1.slewRADec import SlewRADec
from tcspy.action.level1.slewAltAz import SlewAltAz
from tcspy.action.level1.exposure import Exposure
from tcspy.action.level2.singleobservation import SingleObservation
from tcspy.utils.exception import *
#%%
class SequentialObservation(Interface_Runnable, Interface_Abortable):
    def __init__(self, 
                 Integrated_device : IntegratedDevice,
                 abort_action : Event):
        self.IDevice = Integrated_device
        self.IDevice_status = DeviceStatus(self.IDevice)
        self.abort_action = abort_action
        self._log = mainLogger(unitnum = self.IDevice.unitnum, logger_name = __name__+str(self.IDevice.unitnum)).log()

    def _get_exposure_info(self,
                           filter_str : str,
                           exptime_str : str,
                           count_str : str,
                           binning_str : str = '1'):
        filter_list = filter_str.split(',')
        exptime_list = exptime_str.split(',')
        count_list = count_str.split(',')
        binning_list = binning_str.split(',')
        exposure_info = dict()
        exposure_info['filter'] = filter_list
        exposure_info['exptime'] = exptime_list
        exposure_info['count'] = count_list
        exposure_info['binning'] = binning_list
        len_filt = len(filter_list)        
        for name, value in exposure_info.items():
            len_value = len(value)
            if len_filt != len_value:
                exposure_info[name] = [value[0]] * len_filt
        return exposure_info

    def run(self,
            exptime_str : float,
            filter_str : str,
            count_str : str,
            binning_str : str = '1',
            imgtype : str = 'Light',
            ra : float = None,
            dec : float = None,
            alt : float = None,
            az : float = None,
            target_name : str = None,
            target_obsmode : str = 'Single',
            autofocus_before_start : bool = False,
            autofocus_when_filterchange : bool = False
            ):
        # Check condition of the instruments for this Action
        status_filterwheel = self.IDevice_status.filterwheel
        status_camera = self.IDevice_status.camera
        status_telescope = self.IDevice_status.telescope
        trigger_abort_disconnected = False
        if status_camera.lower() == 'disconnected':
            trigger_abort_disconnected = True
            self._log.critical(f'Camera is disconnected. Action "{type(self).__name__}" is not triggered')
        if status_filterwheel.lower() == 'disconnected':
            trigger_abort_disconnected = True
            self._log.critical(f'Filterwheel is disconnected. Action "{type(self).__name__}" is not triggered')
        if status_telescope.lower() == 'disconnected':
            trigger_abort_disconnected = True
            self._log.critical(f'Telescope is disconnected. Action "{type(self).__name__}" is not triggered') 
        if trigger_abort_disconnected:
            return ConnectionException(f'[{type(self).__name__}] is failed: devices are disconnected.')
        # Done
        
        # Abort when triggered
        if self.abort_action.is_set():
            self.abort()
            self._log.warning(f'[{type(self).__name__}] is aborted.')
            return  AbortionException(f'[{type(self).__name__}] is aborted.')
                
        # SingleObservation
        exposure_info = self._get_exposure_info(filter_str= filter_str, exptime_str = exptime_str, count_str= count_str, binning_str= binning_str)
        
        target = mainTarget(unitnum = self.IDevice.unitnum, observer = self.IDevice.observer, target_ra = ra, target_dec = dec, target_alt = alt, target_az = az, target_name = target_name, target_obsmode = 'Spec')                
        
        
            
        
    def abort(self):
        status_filterwheel = self.IDevice_status.filterwheel
        status_camera = self.IDevice_status.camera
        status_telescope = self.IDevice_status.telescope
        if status_filterwheel.lower() == 'busy':
            self.IDevice.filterwheel.abort()
        if status_camera.lower() == 'busy':
            self.IDevice.camera.abort()
        if status_telescope.lower() == 'busy':
            self.IDevice.telescope.abort()
    