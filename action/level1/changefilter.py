#%%
from threading import Event

from tcspy.interfaces import *
from tcspy.devices import IntegratedDevice
from tcspy.devices import DeviceStatus
from tcspy.utils.logger import mainLogger
#%%

class ChangeFilter(Interface_Runnable, Interface_Abortable):
    
    def __init__(self, 
                 Integrated_device : IntegratedDevice,
                 abort_action : Event):
        self.IDevice = Integrated_device
        self.IDevice_status = DeviceStatus(self.IDevice)
        self.abort_action = abort_action
        self._log = mainLogger(unitnum = self.IDevice.unitnum, logger_name = __name__+str(self.IDevice.unitnum)).log()

    def run(self,
            filter_ : str):
        # Check device connection
        if self.IDevice_status.filterwheel.lower() == 'disconnected':
            self._log.critical(f'Filterwheel is disconnected. Action "{type(self).__name__}" is not triggered')
            return 
        
        # If not aborted, execute the action
        if not self.abort_action.is_set():
            self._log.info(f'[{type(self).__name__}] is triggered.')
            if self.IDevice_status.filterwheel.lower() == 'idle':
                self.IDevice.filterwheel.move(filter_ = filter_)
            if not self.abort_action.is_set():
                self._log.info(f'[{type(self).__name__}] is finished.')
            else:
                self._log.warning(f'[{type(self).__name__}] is aborted.')
        else:
            self.abort()
    
    def abort(self):
        return
