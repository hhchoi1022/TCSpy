

#%%
from tcspy.utils.target import MultiTarget
from tcspy.configuration import mainConfig
from tcspy.utils.target.db_target import SQL_Connector
from tcspy.devices.observer import mainObserver

from astropy.table import Table 
from astropy.time import Time
import astropy.units as u
from astropy.coordinates import SkyCoord
import numpy as np
from astroplan import observability_table
from astroplan import AltitudeConstraint, MoonSeparationConstraint

# %%

class DailyTarget(mainConfig):
    
    def __init__(self,
                 utctime : Time = Time.now(),
                 tbl_name : str = 'Daily'):
        super().__init__()       
        self.observer = mainObserver(unitnum= 1)
        self.tblname = tbl_name
        self.sql = SQL_Connector(id_user = self.config['DB_ID'], pwd_user= self.config['DB_PWD'], host_user = self.config['DB_HOSTIP'], db_name = self.config['DB_NAME'])
        self.constraints = self._set_constrints()
        self.utctime = utctime
        self.obsinfo = self._set_obs_info(utctime = utctime)
        self.obsnight = self._set_obsnight(utctime = utctime, horizon_prepare = self.config['TARGET_SUNALT_PREPARE'], horizon_astro = self.config['TARGET_SUNALT_ASTRO'])

    def _set_obs_info(self,
                      utctime : Time = Time.now()):
        class info: pass
        info.moon_phase = self.observer.moon_phase(utctime)
        info.moon_radec = self.observer.moon_radec(utctime)
        info.sun_radec = self.observer.sun_radec(utctime)
        info.observer_info = self.observer.get_status()
        info.observer_astroplan = self.observer._observer
        info.is_night = self.observer.is_night(utctime)
        return info
    
    def _set_obsnight(self,
                      utctime : Time = Time.now(),
                      horizon_prepare : float = -5,
                      horizon_astro : float = -18):
        class night: pass
        night.sunrise_prepare = self.observer.tonight(time = utctime, horizon = horizon_prepare)[1]
        night.sunset_prepare = self.observer.sun_settime(night.sunrise_prepare, mode = 'previous', horizon= horizon_prepare)
        night.sunrise_astro = self.observer.sun_risetime(night.sunrise_prepare, mode = 'previous', horizon= horizon_astro)
        night.sunset_astro = self.observer.sun_settime(night.sunrise_prepare, mode = 'previous', horizon= horizon_astro)
        night.midnight = Time((night.sunset_astro.jd + night.sunrise_astro.jd)/2, format = 'jd')
        night.time_inputted = utctime
        night.current = Time.now()
        return night

    def _set_constrints(self):
        class constraint: pass
        constraint_astroplan = []
        if (self.config['TARGET_MINALT'] != None) & (self.config['TARGET_MAXALT'] != None):
            constraint_altitude = AltitudeConstraint(min = self.config['TARGET_MINALT'] * u.deg, max = self.config['TARGET_MAXALT'] * u.deg, boolean_constraint = False)
            constraint_astroplan.append(constraint_altitude)
            constraint.minalt = self.config['TARGET_MINALT']
            constraint.maxalt = self.config['TARGET_MAXALT']
        if self.config['TARGET_MOONSEP'] != None:
            constraint_gallatitude = MoonSeparationConstraint(min = self.config['TARGET_MOONSEP'] * u.deg, max = None)
            constraint_astroplan.append(constraint_gallatitude)
            constraint.moon_separation = self.config['TARGET_MOONSEP']
        constraint.astroplan = constraint_astroplan
        return constraint

    def _get_moonsep(self,
                     multitarget : MultiTarget):
        '''
        multitarget = MultiTarget(observer = self.observer, 
                            targets_ra = target_tbl['RA'], 
                            targets_dec = target_tbl['De'],    
                            targets_name = target_tbl['objname'])
        '''
        all_coords = multitarget.coordinate
        moon_coord = SkyCoord(ra =self.obsinfo.moon_radec.ra.value, dec = self.obsinfo.moon_radec.dec.value, unit = 'deg')
        moonsep = np.array(SkyCoord.separation(all_coords, moon_coord).value).round(2)
        return moonsep
    
    def _get_transit_besttime(self,
                              multitarget : MultiTarget):
        
        all_time_hourangle = multitarget.hourangle(self.obsnight.midnight)
        all_hourangle_converted = [hourangle if (hourangle -12 < 0) else hourangle-24 for hourangle in all_time_hourangle.value]
        all_target_altaz_at_sunset = multitarget.altaz(utctimes=self.obsnight.sunset_astro)
        all_target_altaz_at_sunrise = multitarget.altaz(utctimes=self.obsnight.sunrise_astro)
        all_transittime = self.obsnight.midnight - all_hourangle_converted * u.hour
        all_besttime = []
        all_maxalt = []
        for i, target_info in enumerate(zip(all_transittime, multitarget.coordinate)):
            target_time_transit, target_coord = target_info
            if (target_time_transit > self.obsnight.sunset_astro) & (target_time_transit < self.obsnight.sunrise_astro):
                maxaltaz = self.obsinfo.observer_astroplan.altaz(target_time_transit, target = target_coord)
                maxalt = np.round(maxaltaz.alt.value,2)
                all_besttime.append(target_time_transit)
            else:
                sunset_alt = all_target_altaz_at_sunset[i].alt.value
                sunrise_alt = all_target_altaz_at_sunrise[i].alt.value
                maxalt = np.round(np.max([sunset_alt, sunrise_alt]),2)
                if sunset_alt > sunrise_alt:
                    all_besttime.append(self.obsnight.sunset_astro)
                else:
                    all_besttime.append(self.obsnight.sunrise_astro)
            all_maxalt.append(maxalt)
        return all_transittime, all_maxalt, Time(all_besttime)

    def _get_target_observable(self,
                               multitarget : MultiTarget,
                               fraction_observable : float = 0.1):
        '''
        multitarget = MultiTarget(observer = self.observer, 
                                  targets_ra = target_tbl['RA'], 
                                  targets_dec = target_tbl['De'],    
                                  targets_name = target_tbl['objname'])
        '''
        observability_tbl = observability_table(constraints = self.constraints, observer = multitarget._astroplan_observer, targets = multitarget.coordinate , time_range = [self.obsnight.sunset_astro, self.obsnight.sunrise_astro], time_grid_resolution = 20 * u.minute)
        obs_tbl['fraction_obs'] = ['%.2f'%fraction for fraction in observability_tbl['fraction of time observable']]
        key = observability_tbl['fraction of time observable'] > fraction_observable
        obs_tbl = obs_tbl[key]
    
    def initialize(self, 
                   initialize_all : bool = False):
        self.sql.connect(db_name = 'target')
        target_tbl_all = self.data
        
        # If there is targets with no "id", set ID for each target
        rows_to_update_id = [any(row[name] is None for name in ['id']) for row in target_tbl_all]
        if np.sum(rows_to_update_id) > 0:
            self.sql.set_data_id(tbl_name = self.tblname, update_all = False)
            target_tbl_all = self.data
        
        target_tbl_to_update = target_tbl_all
        column_names_to_update = ['risetime', 'transittime', 'settime', 'besttime', 'maxalt', 'moonsep']
        
        # If initialize_all == False, filter the target table that requires update 
        if not initialize_all:
            rows_to_update = [any(row[name] is None for name in column_names_to_update) for row in target_tbl_all]
            target_tbl_to_update =  target_tbl_all[rows_to_update]
        
        if len(target_tbl_to_update) == 0:
            self.sql.close()
            return 
        
        multitarget = MultiTarget(observer = self.observer,
                                  targets_ra = target_tbl_to_update['RA'],
                                  targets_dec = target_tbl_to_update['De'],
                                  targets_name = target_tbl_to_update['objname'])
        
        risetime = multitarget.risetime(utctime = self.utctime, mode = 'nearest', horizon = self.config['TARGET_MINALT'], n_grid_points= 50)
        settime = multitarget.settime(utctime = self.utctime)
        transittime, maxalt, besttime = self._get_transit_besttime(multitarget = multitarget)
        moonsep = self._get_moonsep(multitarget = multitarget)
        values_updated = np.array([risetime.isot, transittime.isot, settime.isot, besttime.isot, maxalt, moonsep]).T
        
        for i, value in enumerate(values_updated):
            target_to_update = target_tbl_to_update[i]    
            self.sql.update_row(tbl_name = self.tblname, update_value = value, update_key = column_names_to_update, id_value= target_to_update['id'], id_key = 'id')
        self.sql.close()
    
    def _scorer(self,
                utctime : Time,
                target_tbl : Table,
                duplicate : bool = False):
        
        target_tbl_for_scoring = target_tbl
        if not duplicate:
            unscheduled_idx = (target_tbl['status'] == 'unscheduled')
            target_tbl_for_scoring = target_tbl[unscheduled_idx]
        
        multitarget = MultiTarget(observer = self.observer,
                                  targets_ra = target_tbl_for_scoring['RA'],
                                  targets_dec = target_tbl_for_scoring['De'],
                                  targets_name = target_tbl_for_scoring['objname'])
        
        def calc_totexptime(target):
        
        multitarget_altaz = multitarget.altaz(utctimes = utctime)
        multitarget_alt = multitarget_altaz.alt.value
        multitarget_priority = target_tbl_for_scoring['priority'].astype(float)
        
        score = np.ones(len(target_tbl_for_scoring))
        # Applying constraints
        constraint_moonsep = target_tbl['moonsep'].astype(float) > self.constraints.moon_separation
        score *= constraint_moonsep
        
        constraint_altitude = multitarget_alt > self.constraints.minalt
        score *= constraint_altitude
        
        constraint_altitude = multitarget_alt < self.constraints.maxalt
        score *= constraint_altitude
        
        constraint_set = utctime < self.obsnight.sunrise_astro
        
        constraint_night = self.observer.is_night(utctimes = utctime)
        score *= constraint_night
        
        # Scoring
        weight_sum = self.config['TARGET_WEIGHT_ALT'] + self.config['TARGET_WEIGHT_PRIORITY']
        weight_alt = self.config['TARGET_WEIGHT_ALT'] / weight_sum
        weight_priority = self.config['TARGET_WEIGHT_PRIORITY'] / weight_sum
        
        multitarget_alt = np.array([0 if target_alt <= 0 else target_alt for target_alt in multitarget_alt])
        score_relative_alt = weight_alt * np.clip(0, 1, (multitarget_alt) / (np.abs(target_tbl_for_scoring['maxalt'])))
        
        highest_priority = np.max(multitarget_priority)
        score_weight = weight_priority* (multitarget_priority / highest_priority)

        score_all = (score_relative_alt  + score_weight) 
        score *= score_all
        idx_best = np.argmax(score)
        score_best = score[idx_best]
        return target_tbl_for_scoring[idx_best], score_best
    
    def best_target(self,
                    utctime : Time = Time.now()):
        self.sql.connect(db_name = 'target')
        all_targets = self.data
        column_names_for_scoring = ['risetime', 'transittime', 'settime', 'besttime', 'maxalt', 'moonsep']
        
        # If one of the targets do not have the required information, calculate
        rows_to_update = [any(row[name] is None for name in column_names_for_scoring) for row in all_targets]
        target_tbl_to_update =  all_targets[rows_to_update]
        if len(target_tbl_to_update) > 0:
            self.initialize(initialize_all= False)
            print(f'{len(target_tbl_to_update)} targets are updated')
        
        import time
        start = time.perf_counter()
        all_targets = self.data
        #all_targets['']
        target_best, target_score = self._scorer(utctime = utctime, target_tbl = all_targets, duplicate = False)        
        print(time.perf_counter() - start)    
        self.sql.close()
        return target_best, target_score
    
    @property
    def data(self):
        self.sql.connect(db_name = 'target')
        return self.sql.get_data(tbl_name = self.tblname, select_key= '*')

    

# %%
D =  DailyTarget()
# %%
A = D.initialize(initialize_all= False)
# %%
D.best_target(Time.now() + 10 * u.hour)
#%%
D._get_moonsep(target_tbl =  D.get_data()[150:220])
# %%
D._get_maxaltaz(target_tbl =  D.get_data()[150:220])[1]
# %%
Time(D._get_maxaltaz(target_tbl = D.get_data()[150:220])[2]).isot
# %%
D.get_data()
# %%
import matplotlib.pyplot as plt
plt.plot(Time(D._get_maxaltaz(target_tbl = D.get_data()[150:220])[2]).value)
# %%
D.get_data()[200:250]['RA']
# %%
for value in D.get_data()[150:220]:
    print(value['RA'], ' ', value['De'])
# %%
