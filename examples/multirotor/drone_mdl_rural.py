# -*- coding: utf-8 -*-
"""
File name: quad_mdl.py
Author: Daniel Hulse
Created: June 2019, revised Nov 2022
Description: A fault model of a multi-rotor drone.
"""
import matplotlib.pyplot as plt
from shapely.geometry.polygon import Polygon
from shapely.geometry import Point
from examples.multirotor.drone_mdl_hierarchical import AffectDOFArch, OverallAffectDOFState
import numpy as np
from fmdtools.define.parameter import Parameter
from fmdtools.define.state import State
from fmdtools.define.mode import Mode
from fmdtools.define.block import FxnBlock, Component, CompArch
from fmdtools.define.flow import Flow
from fmdtools.define.model import Model
from fmdtools.define.environment import Grid, GridParam, Environment
from fmdtools.sim.approach import SampleApproach
from fmdtools.sim import propagate
from fmdtools.analyze.result import History

import fmdtools.analyze as an

from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from examples.multirotor.drone_mdl_dynamic import finddist, vectdist, vectdir, inrange
from examples.multirotor.drone_mdl_static import EE, Force, Control, DesTraj, DOFs
from examples.multirotor.drone_mdl_static import DistEE
from examples.multirotor.drone_mdl_static import StoreEEState
from recordclass import asdict

# DEFINE PARAMETERS


class ResPolicy(Parameter, readonly=True):
    bat:   str = 'to_home'
    bat_set = ('to_nearest', 'to_home', 'emland', 'land', 'move', 'continue')
    line:   str = 'emland'
    line_set = ('to_nearest', 'to_home', 'emland', 'land', 'move', 'continue')


class DroneEnvironmentGridParam(GridParam):
    """
    Defines the grid parameters, including resolution as well as number of allowed,
    unsafe, and occupied spaces, max height of the buildings, and road width.
    """
    x_size: int = 16
    y_size: int = 16
    blocksize: float = 10.0
    loc: str = 'rural'


class SightGrid(Grid):
    _init_p = DroneEnvironmentGridParam
    _state_viewed = (bool, False)
    _feature_target = (bool, False)
    _point_start = (0, 0)
    _point_safe = (0, 50)
    def init_properties(self, *args, **kwargs):
        self.set_range("target", True, 0, 150, 10, 160)


class DroneEnvironment(Environment):
    _init_g = SightGrid
    _init_p = DroneEnvironmentGridParam



class DronePhysicalParameters(Parameter, readonly=True):
    bat:        str = 'monolithic'
    bat_set = ('monolithic', 'series-split', 'parallel-split', 'split-both')
    linearch:   str = 'quad'
    linearch_set = ('quad', 'hex', 'oct')
    batweight:  float = 0.4
    archweight: float = 1.2
    archdrag:   float = 0.95
    def __init__(self, *args, **kwargs):
        args = self.get_true_fields(*args, **kwargs)
        args[2] = {'monolithic': 0.4, 'series-split': 0.5,
                   'parallel-split': 0.5, 'split-both': 0.6}[args[0]]
        args[3] = {'quad': 1.2, 'hex': 1.6, 'oct': 2.0}[args[1]]
        args[4] = {'quad': 0.95, 'hex': 0.85, 'oct': 0.75}[args[1]]
        super().__init__(*args)


class DroneParam(Parameter, readonly=True):
    """Parameters for the Drone optimization model"""
    respolicy:  ResPolicy = ResPolicy()
    flightplan: tuple = ((0, 0, 0),  # flies through a few points and back to the start
                         (0, 0, 100),
                         (100, 0, 100),
                         (100, 100, 100),
                         (150, 150, 100),
                         (0, 0, 100),
                         (0, 0, 0))
    env_param: DroneEnvironmentGridParam = DroneEnvironmentGridParam()
    phys_param: DronePhysicalParameters = DronePhysicalParameters()


# DEFINE FLOWS
class HSigState(State):
    hstate: str = 'nominal'


class HSig(Flow):
    _init_s = HSigState


class RSigState(State):
    mode:   str = 'continue'


class RSig(Flow):
    _init_s = RSigState

# DEFINE FUNCTIONS


class BatState(State):
    soc:  float = 100.0
    ee_e: float = 1.0
    e_t:  float = 1.0
    """
    Battery States. Includes:
        soc: float
            State of charge, with values (0-100)
        e_t: float
            Power transference with nominal value 1.0
    """


class BatMode(Mode):
    failrate = 1e-4
    faultparams = {'short': (0.2, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 100),
                   'degr': (0.2, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 100),
                   'break': (0.2, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 100),
                   'nocharge': (0.6, {"taxi": 0.7, "move": 0.2, "land": 0.1}, 100),
                   'lowcharge': (0.4, {"taxi": 0.5, "move": 0.2, "land": 0.3}, 100)}
    key_phases_by = 'plan_path'
    """
    Battery Modes. Includes:
        - short: Fault
            inability to transfer power
        - degr: Fault
            less power tranferrence
        - break: Fault
            inability to transfer power
        - nocharge: Fault
            zero state of charge (need a way to trigger these modes)
        - lowcharge: Fault
            state of charge of 20
    """


class BatParam(Parameter):
    avail_eff:  float = 0.0
    maxa:       float = 0.0
    amt:        float = 0.0
    weight:     float = 0.1
    drag:       float = 0.0
    series:     int = 1
    parallel:   int = 1
    voltage:    float = 12.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.avail_eff = 1/self.parallel
        self.maxa = 2/self.series
        self.amt = 60*4.200/(self.weight*170/(self.drag*self.voltage))


class Battery(Component):
    _init_s = BatState
    _init_m = BatMode
    _init_p = BatParam

    def behavior(self, fs, ee_outr, time):
        # If current is too high, battery breaks.
        if fs < 1.0 or ee_outr > self.p.maxa:
            self.m.add_fault('break')

        # Determine transference state based on faults
        if self.m.has_fault('short'):
            self.s.e_t = 0.0
        elif self.m.has_fault('break'):
            self.s.e_t = 0.0
        elif self.m.has_fault('degr'):
            self.s.e_t = 0.5*self.p.avail_eff
        else:
            self.s.e_t = self.p.avail_eff

        # Increment power use/soc (once per timestep)
        if time > self.t.time:
            self.s.inc(soc=-100*ee_outr*self.p.parallel *
                       self.p.series*(time-self.t.time)/self.p.amt)
            self.t.time = time

        # Calculate charge modes/values
        if self.s.soc < 20:
            self.m.add_fault('lowcharge')
        if self.s.soc < 1:
            self.m.replace_fault('lowcharge', 'nocharge')
            self.s.put(soc=0.0, e_t=0.0)
            er_res = ee_outr
        else:
            er_res = 0.0
        return self.s.e_t, self.s.soc, er_res


class BatArch(CompArch):
    archtype:   str = 'monolithic'
    batparams:  dict = {}  # weight, cap, voltage, drag_factor
    weight:     float = 0.0
    drag:       float = 0.0
    series:     int = 1
    parallel:   int = 1
    voltage:    float = 12.0
    drag:       float = 0.0
    """
    Battery architecture. Defined by archtype parameter with options:
        - 'monolythic':
            Single Battery
        - 'series-split':
            Two batteries put in series
        - 'parallel-split':
            two batteries put in parallel
        - 'split-both':
            four batteries arranged in a series-parallel configuration
    """

    def __init__(self, *args, **kwargs):
        archtype = self.get_true_field('archtype', *args, **kwargs)
        weight = self.get_true_field('weight', *args, **kwargs)
        drag = self.get_true_field('drag', *args, **kwargs)
        if archtype == 'monolithic':
            batparams = {"series": 1, "parallel": 1,
                         "voltage": 12.0, "weight": weight, "drag": drag}
            compnames = ['s1p1']
        elif archtype == 'series-split':
            batparams = {'series': 2, 'parallel': 1,
                         'voltage': 12.0, "weight": weight, "drag": drag}
            compnames = ['s1p1', 's2p1']
        elif archtype == 'parallel-split':
            batparams = {'series': 1, 'parallel': 2,
                         'voltage': 12.0, "weight": weight, "drag": drag}
            compnames = ['s1p1', 's1p2']
        elif archtype == 'split-both':
            batparams = {'series': 2, 'parallel': 2,
                         'voltage': 12.0, "weight": weight, "drag": drag}
            compnames = ['s1p1', 's1p2', 's2p1', 's2p2']
        else:
            raise Exception("Invalid battery architecture")
        kwargs.update(batparams)
        super().__init__(*args, **kwargs)
        self.make_components(Battery, *compnames, p=batparams)


class StoreEEMode(Mode):
    failrate = 1e-4
    faultparams = {'nocharge':  (0.2, {"taxi": 0.6, "move": 0.2, "land": 0.2}, 0),
                   'lowcharge': (0.7, {"taxi": 0.6, "move": 0.2, "land": 0.2}, 0)}
    key_phases_by = "plan_path"


class StoreEE(FxnBlock):
    __slots__ = ('hsig_bat', 'ee_1', 'force_st')
    _init_s = StoreEEState
    _init_m = StoreEEMode
    _init_c = BatArch
    _init_hsig_bat = HSig
    _init_ee_1 = EE
    _init_force_st = Force
    """
    Class defining energy storage function with battery architecture.
    """

    def condfaults(self, time):
        if self.s.soc < 20:
            self.m.add_fault('lowcharge')
        if self.s.soc < 1:
            self.m.replace_fault('lowcharge', 'nocharge')
        if self.m.has_fault('lowcharge'):
            for batname, bat in self.c.components.items():
                bat.s.limit(soc = (0, 19))
        elif self.m.has_fault('nocharge'):
            for batname, bat in self.c.components.items():
                bat.s.soc = 0

    def behavior(self, time):
        ee, soc = {}, {}
        rate_res = 0
        for batname, bat in self.c.components.items():
            ee[bat.name], soc[bat.name], rate_res = \
                bat.behavior(self.force_st.s.support, self.ee_1.s.rate /
                             (self.c.series*self.c.parallel)+rate_res, time)
        # need to incorporate max current draw somehow + draw when reconfigured
        if self.c.archtype == 'monolithic':
            self.ee_1.s.effort = ee['s1p1']
        elif self.c.archtype == 'series-split':
            self.ee_1.s.effort = np.max(list(ee.values()))
        elif self.c.archtype == 'parallel-split':
            self.ee_1.s.effort = np.sum(list(ee.values()))
        elif self.c.archtype == 'split-both':
            e = list(ee.values())
            e.sort()
            self.ee_1.effort = e[-1]+e[-2]
        self.s.soc = np.mean(list(soc.values()))
        if self.m.any_faults() and not self.m.has_fault("dummy"):
            self.hsig_bat.s.hstate = 'faulty'
        else:
            self.hsig_bat.s.hstate = 'nominal'


class HoldPayloadMode(Mode):
    failrate = 1e-6
    faultparams = {'break': (0.2, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 1000),
                   'deform': (0.8, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 1000)}
    key_phases_by = 'plan_path'
    """
    Landing Gear Modes. Has faults:
        - break: Fault
            provides no support to the body and lines
        - deform: Fault
            support is less than desired
    """


class HoldPayloadState(State):
    force_gr:   float = 1.0
    """
    Landing Gear States. Has values:
        - force_gr: float
            Force from the ground
    """


class HoldPayload(FxnBlock):
    __slots__ = ('dofs', 'force_st', 'force_lin')
    _init_m = HoldPayloadMode
    _init_s = HoldPayloadState
    _init_dofs = DOFs
    _init_force_st = Force
    _init_force_lin = Force

    def at_ground(self):
        return self.dofs.s.z <= 0.0

    def dynamic_behavior(self, time):
        if self.at_ground():
            self.s.force_gr = min(-0.5, (self.dofs.s.vertvel -
                                  self.dofs.s.planvel)/(60*7.5))
        else:
            self.s.force_gr = 0.0
        if abs(self.s.force_gr/2) > 1.0:
            self.m.add_fault('break')
        elif abs(self.s.force_gr/2) > 0.8:
            self.m.add_fault('deform')

        # need to transfer FG to FA & FS???
        if self.m.has_fault('break'):
            self.force_st.s.support = 0.0
        elif self.m.has_fault('deform'):
            self.force_st.s.support = 0.5
        else:
            self.force_st.s.support = 1.0
        self.force_lin.s.assign(self.force_st.s, 'support')


class ManageHealthMode(Mode):
    failrate = 1e-6
    faultparams = {'lostfunction': (0.05, {"taxi": 0.3, "move": 0.3, "land": 0.3}, 1000)}
    key_phases_by = "plan_path"
    """
    Has modes:
        - lostfunction: Fault
            Inability to sense health and thus reconfigure the system
    """


class ManageHealth(FxnBlock):
    __slots__ = ('force_st', 'ee_ctl', 'hsig_dofs', 'hsig_bat', 'rsig_traj')
    _init_m = ManageHealthMode
    _init_p = ResPolicy
    _init_force_st = Force
    _init_ee_ctl = EE
    _init_hsig_dofs = HSig
    _init_hsig_bat = HSig
    _init_rsig_traj = RSig

    def condfaults(self, time):
        if self.force_st.s.support < 0.5 or self.ee_ctl.s.effort > 2.0:
            self.m.add_fault('lostfunction')

    def behavior(self, time):
        if self.m.has_fault('lostfunction'):
            self.rsig_traj.s.mode = 'continue'
        elif self.hsig_dofs.s.hstate == 'faulty':
            self.rsig_traj.s.mode = self.p.line
        elif self.hsig_bat.s.hstate == 'faulty':
            self.rsig_traj.s.mode = self.p.bat
        else:
            self.rsig_traj.s.mode = 'continue'


class AffectMode(Mode):
    key_phases_by = 'plan_path'


class AffectDOF(FxnBlock):  # ee_mot,ctl,dofs,force_lin hsig_dofs, RSig_dofs
    __slots__ = ('ee_mot', 'ctl', 'hsig_dofs', 'dofs', 'des_traj', 'force_lin')
    _init_c = AffectDOFArch
    _init_s = OverallAffectDOFState
    _init_m = AffectMode
    _init_ee_mot = EE
    _init_ctl = Control
    _init_hsig_dofs = HSig
    _init_dofs = DOFs
    _init_des_traj = DesTraj
    _init_force_lin = Force

    def behavior(self, time):
        air, ee_in = {}, {}
        for linname, lin in self.c.components.items():
            air[lin.name], ee_in[lin.name] = lin.behavior(self.ee_mot.s.effort,
                                                          self.ctl,
                                                          self.c.forward[linname],
                                                          self.force_lin.s.support)

        if any(value >= 10 for value in ee_in.values()):
            self.ee_mot.s.rate = 10
        elif any(value != 0.0 for value in ee_in.values()):
            self.ee_mot.s.rate = sum(ee_in.values()) / \
                len(ee_in)  # should it really be max?
        else:
            self.ee_mot.s.rate = 0.0

        self.s.lrstab = (sum([air[comp] for comp in self.c.lr_dict['l']]) -
                         sum([air[comp] for comp in self.c.lr_dict['r']]))/len(air)
        self.s.frstab = (sum([air[comp] for comp in self.c.fr_dict['r']]) -
                         sum([air[comp] for comp in self.c.fr_dict['f']]))/len(air)

        if abs(self.s.lrstab) >= 0.25 or abs(self.s.frstab) >= 0.75:
            self.dofs.s.put(uppwr=0.0, planpwr=0.0)
        else:
            self.dofs.s.put(uppwr=np.mean(list(air.values())),
                            planpwr=self.ctl.s.forward)

        if self.m.any_faults():
            self.hsig_dofs.s.hstate = 'faulty'
        else:
            self.hsig_dofs.s.hstate = 'nominal'

    def calc_vel(self):
        # calculate velocities from power
        self.dofs.s.put(vertvel=300*(self.dofs.s.uppwr-1.0),
                        planvel=600*self.dofs.s.planpwr)  # 600 m/m = 23 mph
        self.dofs.s.roundto(vertvel=0.001, planvel=0.001)

    def inc_takeoff(self):
        # can only take off at ground
        if self.dofs.s.z <= 0.0:
            self.dofs.s.put(planvel=0.0, vertvel=max(0, self.dofs.s.vertvel))

    def inc_falling(self, min_fall_dist=300.0):
        # if falling, it can't reach the destination if it hits the ground first
        plan_dist = np.sqrt(self.des_traj.s.x**2 + self.des_traj.s.y**2+0.0001)
        if self.dofs.s.vertvel < -self.dofs.s.z and -self.dofs.s.vertvel > self.dofs.s.planvel:
            plan_dist = plan_dist*self.dofs.s.z/(-self.dofs.s.vertvel+0.001)
        self.dofs.s.limit(vertvel=(-min_fall_dist/self.t.dt, 300.0),
                          planvel=(0.0, plan_dist/self.t.dt))

    def inc_pos(self):
        # increment x,y,z
        vec_factor = np.sqrt(self.des_traj.s.x**2 + self.des_traj.s.y**2+0.0001)
        norm_vel = self.dofs.s.planvel * self.t.dt / vec_factor
        self.dofs.s.inc(x=norm_vel*self.des_traj.s.x,
                        y=norm_vel*self.des_traj.s.y,
                        z=self.dofs.s.vertvel*self.t.dt)
        self.dofs.s.roundto(x=0.01, y=0.01, z=0.01)

    def dynamic_behavior(self, time):
        self.calc_vel()
        self.inc_takeoff()
        self.inc_falling(min_fall_dist=self.dofs.s.z)
        self.inc_pos()



class CtlDOFMode(Mode):
    failrate = 1e-5
    faultparams = {'noctl':   (0.2, {"taxi": 0.6, "move": 0.3, "land": 0.1}, 1000),
                   'degctl':  (0.8, {"taxi": 0.6, "move": 0.3, "land": 0.1}, 1000)}
    exclusive = True
    key_phases_by = 'plan_path'
    mode:   str = 'nominal'
    """
    Controller modes:
        noctl: Fault
            No control transference (throttles set to zero)
        degctl: Fault
            Poor control transference (throttles set to 0.5)
    """
from drone_mdl_dynamic import CtlDOF as CtlDOFDyn

class CtlDOF(CtlDOFDyn):
    _init_m = CtlDOFMode

# =============================================================================
# class CtlDOF(FxnBlock):
#     __slots__ = ('ctl', 'ee_ctl', 'des_traj', 'force_st', 'dofs')
#     _init_s = CtlDOFState
#     _init_m = CtlDOFMode
#     _init_ctl = Control
#     _init_ee_ctl = EE
#     _init_des_traj = DesTraj
#     _init_force_st = Force
#     _init_dofs = DOFs
# 
#     def condfaults(self, time):
#         if self.force_st.s.support < 0.5:
#             self.m.add_fault('noctl')
# 
#     def behavior(self, time):
#         if self.m.has_fault('noctl'):
#             self.s.cs = 0.0
#         elif self.m.has_fault('degctl'):
#             self.s.cs = 0.5
#         else:
#             self.s.cs = 1.0
# 
#         # set throttle
#         self.s.upthrottle = 1+self.des_traj.s.z/(50*5)
#         self.s.throttle = np.sqrt(self.des_traj.s.x**2+self.des_traj.s.y**2)/(60*10)
#         self.s.limit(throttle=(0, 1), upthrottle=(0, 2))
# 
#         # send control signals
#         self.ctl.s.forward = self.ee_ctl.s.effort*self.s.cs*self.s.throttle*self.des_traj.s.power
#         self.ctl.s.upward = self.ee_ctl.s.effort*self.s.cs*self.s.upthrottle*self.des_traj.s.power
# 
#     def dynamic_behavior(self, time):
#         self.s.vel = self.dofs.s.vertvel
# =============================================================================


class ViewEnvironment(FxnBlock):
    """Camera for the drone. Determins which aspects of the environment are viewed."""
    _init_dofs = DOFs
    _init_environment = DroneEnvironment

    def behavior(self, time):
        width = self.dofs.s.z
        height = self.dofs.s.z
        self.environment.g.set_range("viewed", True,
                                     self.dofs.s.x - width/2,
                                     self.dofs.s.x + width/2,
                                     self.dofs.s.y - height/2,
                                     self.dofs.s.y + height/2)


class PlanPathMode(Mode):
    failrate = 1e-5
    faultparams = {'noloc': (0.2, {"taxi": 0.6, "move": 0.3, "land": 0.1}, 1000),
                   'degloc': (0.8, {"taxi": 0.6, "move": 0.3, "land": 0.1}, 1000)}
    opermodes = ('taxi', 'to_nearest', 'to_home', 'emland', 'land', 'move')
    mode: str = 'taxi'
    exclusive = False
    key_phases_by = 'self'
    """
    Path planning fault modes:
    - noloc: Fault
        no location data
    - degloc: Fault
        degraded location data
    - taxi:
        off at landing area
    - to_nearest:
        go to the nearest possible landing area
    - to_home:
        flight to the takeoff location
    - emland:
        emergency landing
    - land:
        descent/landing
    - move:
        nominal drone navigation
    """


class PlanPathState(State):
    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0
    dist: float = 0.0
    pt: int = 1
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    ground_height: float = 0.0
    """
    Path planning states:
    - dx, dy, dz: float
        desired trajectory (from current)
    - dist: float
        distance to goal point
    - pt: int
        current goal point (number)
    x, y, z: float
        Current location
    ground_height: float
        Height above the ground (if terrain)
    """


class PlanPath(FxnBlock):
    __slots__ = ('force_st', 'rsig_traj', 'dofs', 'ee_ctl', 'des_traj', 'goals')
    _init_s = PlanPathState
    _init_m = PlanPathMode
    _init_p = DroneParam
    _init_force_st = Force
    _init_rsig_traj = RSig
    _init_dofs = DOFs
    _init_ee_ctl = EE
    _init_des_traj = DesTraj
    """
    Path planning function of the drone. Follows a sequence defined in flightplan.
    """

    def __init__(self, name, flows, **kwargs):
        FxnBlock.__init__(self, name, flows, **kwargs)
        self.init_goals()

    def init_goals(self):
        self.goals = {i: list(vals) for i, vals in enumerate(self.p.flightplan)}

    def condfaults(self, time):
        if self.force_st.s.support < 0.5:
            self.m.add_fault('noloc')

    def behavior(self, t):
        self.s.ground_height = self.dofs.s.z
        self.update_mode(t)
        self.increment_point()
        self.update_dist()
        self.update_traj()

    def update_mode(self, t):
        if not self.m.any_faults():
            # if in reconfigure mode, copy that mode, otherwise complete mission
            if self.rsig_traj.s.mode != 'continue' and not self.m.in_mode("move_em", "emland"):
                self.m.set_mode(self.rsig_traj.s.mode)
            elif self.m.in_mode('taxi') and t < 5 and t > 1:
                self.m.set_mode("move")
            # if mission is over, enter landing mode when you get close
            if self.mission_over():
                if self.dofs.s.z < 1:
                    self.m.set_mode('taxi')
                elif self.s.dist < 10:
                    self.m.set_mode('land')

    def update_dist(self):
        # set the new goal based on the mode
        if self.m.in_mode('emland', 'land'):
            z_down = self.dofs.s.z - self.s.ground_height/2
            self.calc_dist_to_goal([self.dofs.s.x, self.dofs.s.y, z_down])
        elif self.m.in_mode('to_home', 'taxi'):
            self.calc_dist_to_goal(self.goals[0])
        elif self.m.in_mode('to_nearest'):
            self.calc_dist_to_goal([*self.p.safe[:2], 0.0])
        elif self.m.in_mode('move', 'move_em'):
            self.calc_dist_to_goal(self.goals[self.s.pt])
        elif self.m.in_mode('noloc'):
            self.calc_dist_to_goal(self.dofs.s.get('x', 'y', 'z'))
        elif self.m.in_mode('degloc'):
            self.calc_dist_to_goal([self.dofs.s.x, self.dofs.s.y, self.dofs.s.z-1])

    def update_traj(self):
        # send commands (des_traj) if power
        if self.ee_ctl.s.effort < 0.5 or self.m.in_mode('taxi'):
            self.des_traj.s.assign([0.0, 0.0, 0.0, 0.0], 'x', 'y', 'z', 'power')
        else:
            self.des_traj.s.power = 1.0
            self.des_traj.s.assign(self.s, x='dx', y='dy', z='dz')

    def calc_dist_to_goal(self, goal):
        self.s.assign(goal, 'x', 'y', 'z')
        self.s.dist = finddist(self.dofs.s.get('x', 'y', 'z'),
                               self.s.get('x', 'y', 'z'))
        dx, dy, dz = vectdir(self.s.get('x', 'y', 'z'),
                             self.dofs.s.get('x', 'y', 'z'))
        self.s.put(dx=dx, dy=dy, dz=dz)
        self.s.roundto(dx=0.01, dy=0.01, dz=0.01, dist=0.01, x=0.01, y=0.01, z=0.01,
                       ground_height=0.01)

    def mission_over(self):
        return (self.s.pt >= max(self.goals) or
                self.m.in_mode('to_nearest', 'to_home', 'land', 'emland'))

    def increment_point(self):
        # if close to the given point, go to the next point
        if (self.m.in_mode('move', 'move_em')
                and self.s.dist < 10
                and self.s.pt < max(self.goals)):
            self.s.pt += 1

class Drone(Model):
    __slots__ = ('start_area', 'safe_area', 'target_area')
    _init_p = DroneParam
    default_sp = dict(phases=(('taxi', 0, 0),
                              ('move', 1, 11),
                              ('land', 12, 20)),
                      times=(0, 30), units='min')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # add flows to the model
        self.add_flow('force_st', Force)
        self.add_flow('force_lin', Force)
        self.add_flow('hsig_dofs', HSig)
        self.add_flow('hsig_bat', HSig)
        self.add_flow('rsig_traj', RSig)
        self.add_flow('ee_1', EE)
        self.add_flow('ee_mot', EE)
        self.add_flow('ee_ctl', EE)
        self.add_flow('ctl', Control)
        self.add_flow('dofs', DOFs)
        self.add_flow('des_traj', DesTraj)
        self.add_flow('environment', DroneEnvironment, p=self.p.env_param)

        # add functions to the model
        flows = ['ee_ctl', 'force_st', 'hsig_dofs', 'hsig_bat', 'rsig_traj']
        self.add_fxn('manage_health', ManageHealth, *flows, p=asdict(self.p.respolicy))

        store_ee_p = {'archtype': self.p.phys_param.bat,
                      'weight': self.p.phys_param.batweight+self.p.phys_param.archweight,
                      'drag': self.p.phys_param.archdrag}
        self.add_fxn('store_ee', StoreEE, 'ee_1', 'force_st', 'hsig_bat', c=store_ee_p)
        self.add_fxn('dist_ee', DistEE, 'ee_1', 'ee_mot', 'ee_ctl', 'force_st')
        self.add_fxn('affect_dof', AffectDOF, 'ee_mot', 'ctl', 'dofs', 'des_traj',
                     'force_lin', 'hsig_dofs',
                     c={'archtype': self.p.phys_param.linearch})
        self.add_fxn('ctl_dof', CtlDOF, 'ee_ctl', 'des_traj', 'ctl', 'dofs', 'force_st')
        self.add_fxn('plan_path', PlanPath, 'ee_ctl', 'dofs', 'des_traj', 'force_st',
                     'rsig_traj', p=asdict(self.p))
        self.add_fxn('hold_payload', HoldPayload, 'dofs', 'force_lin', 'force_st')
        self.add_fxn('view_environment', ViewEnvironment, 'dofs', 'environment')

        self.build()


    def at_start(self, dofs):
        return self.flows['environment'].g.in_area(dofs.s.x, dofs.s.y, 'start')

    def at_safe(self, dofs):
        return self.flows['environment'].g.in_area(dofs.s.x, dofs.s.y, 'safe')

    def at_dangerous(self, dofs):
        return self.flows['environment'].g.get(dofs.s.x, dofs.s.y, 'target')

    def calc_land_metrics(self, scen, viewed, faulttime):
        metrics = {}
        dofs = self.flows['dofs']
        if self.at_start(dofs):
            landloc = 'nominal'  # nominal landing
        elif self.at_safe(dofs):
            landloc = 'designated'  # emergency safe
        elif self.at_dangerous(dofs):
            landloc = 'over target'  # emergency dangerous
        else:
            landloc = 'outside target'  # emergency unsanctioned
        # need a way to differentiate horizontal and vertical crashes/landings
        if landloc in ['over target', 'outside target']:
            if landloc == "outside target" and self.p.env_param.loc == 'congested':
                loc = 'urban'
            else:
                loc = self.p.env_param.loc
            metrics['body_strikes'] = density_categories[loc]['body strike']['horiz']
            metrics['head_strikes'] = density_categories[loc]['head strike']['horiz']
            metrics['property_restrictions'] = 1
        else:
            metrics['body_strikes'] = 0.0
            metrics['head_strikes'] = 0.0
            metrics['property_restrictions'] = 0
        metrics['safecost'] = calc_safe_cost(metrics, self.p.env_param.loc, faulttime)

        metrics['landcost'] = metrics['property_restrictions'] * \
            propertycost[self.p.env_param.loc]
        metrics['p_safety'] = calc_p_safety(metrics, faulttime)
        metrics['severities'] = {'hazardous': scen.rate * metrics['p_safety'],
                                 'minor': scen.rate * (1 - metrics['p_safety'])}
        return metrics

    def find_classification(self, scen, mdlhist):
        viewed = 0.5 + np.sum(self.flows['environment'].g.viewed*self.flows['environment'].g.target)
        # to fix: need to find fault time more efficiently (maybe in the toolkit?)
        faulttime = self.h.get_fault_time(metric='total')

        land_metrics = self.calc_land_metrics(scen, mdlhist, faulttime)

        # repair costs
        repcost = self.calc_repaircost(max_cost=1500)

        totcost = (land_metrics['landcost']
                   + land_metrics['safecost']
                   + repcost
                   - viewed)

        metrics = {'rate': scen.rate,
                   'cost': totcost,
                   'expected_cost': totcost * scen.rate * 1e5,
                   'repcost': repcost,
                   'viewed value': viewed,
                   'unsafe_flight_time': faulttime,
                   **land_metrics}
        return metrics


pos = {'manage_health': [0.23793980988102348, 1.0551602632416588],
       'store_ee': [-0.9665780995752296, -0.4931538151692423],
       'dist_ee': [-0.1858834234148632, -0.20479989209711924],
       'affect_dof': [1.0334916329507422, 0.6317263653616103],
       'ctl_dof': [0.1835014208949617, 0.32084893189175423],
       'plan_path': [-0.7427736219526058, 0.8569475547950892],
       'hold_payload': [0.74072970715511, -0.7305391093272489]}

bippos = {'manage_health': [-0.23403572483176666, 0.8119063670455383],
          'store_ee': [-0.7099736148158298, 0.2981652748232978],
          'dist_ee': [-0.28748133634190726, 0.32563569654296287],
          'affect_dof': [0.9073412427515959, 0.0466423266443633],
          'ctl_dof': [0.498663257339388, 0.44284186573420836],
          'plan_path': [0.5353654708147643, 0.7413936186204868],
          'hold_payload': [0.329334798653681, -0.17443414674339652],
          'force_st': [-0.2364754675127569, -0.18801548176633154],
          'force_lin': [0.7206415618571647, -0.17552020772024013],
          'hsig_dofs': [0.3209028709788254, 0.04984245810974697],
          'hsig_bat': [-0.6358884586093769, 0.7311076416371343],
          'rsig_traj': [0.18430501738656657, 0.856472541655958],
          'ee_1': [-0.48288657418004555, 0.3017533207866233],
          'ee_mot': [-0.0330582435936827, 0.2878069006385988],
          'ee_ctl': [0.13195069534343862, 0.4818116953414546],
          'ctl': [0.5682663453757308, 0.23385244312813386],
          'dofs': [0.8194232270836169, 0.3883256382522293],
          'des_traj': [0.9276094920710914, 0.6064107724557304]}

# BASE FUNCTIONS


def calc_p_safety(metrics, faulttime):
    p_saf = 1-np.exp(-(metrics['body_strikes'] + metrics['head_strikes']) * 60 /
                     (faulttime+0.001))  # convert to pfh
    return p_saf


def calc_safe_cost(metrics, loc, faulttime):
    safecost = safety_categories['hazardous']['cost'] * \
            (metrics['head_strikes'] + metrics['body_strikes']) + \
            unsafecost[loc] * faulttime
    return safecost


# PLOTTING
def plot_goals(ax, flightplan):
    for goal, loc in enumerate(flightplan):
        ax.text(loc[0], loc[1], loc[2], str(goal), fontweight='bold', fontsize=12)
        ax.plot([loc[0]], [loc[1]], [loc[2]], marker='o',
                 markersize=10, color='red', alpha=0.5)

def plot_env_with_traj3d(hist, mdl):
    fig, ax = show.grid3d(mdl.flows['environment'].g, "target", z="",
                        collections={"start": {"color": "yellow"},
                                     "safe":{"color": "yellow"}})
    fig, ax = show.trajectories(hist, "dofs.s.x", "dofs.s.y", "dofs.s.z",
                                time_groups=['nominal'], time_ticks=1.0,
                                fig=fig, ax=ax)
    plot_goals(ax, mdl.p.flightplan)
    return fig, ax

def plot_env_with_traj(mdlhists, mdl):
    fig, ax = show.grid(mdl.flows['environment'].g, "target",
                        collections={"start": {"color": "yellow"},
                                     "safe":{"color": "yellow"}})
    fig, ax = show.trajectories(mdlhists, "dofs.s.x", "dofs.s.y", fig=fig, ax=ax)
    return fig, ax

# likelihood class schedule (pfh)
p_allowable = {'small airplane': {'no requirement': 'na',
                                  'probable': 1e-3,
                                  'remote': 1e-4,
                                  'extremely remote': 1e-5,
                                  'extremely improbable': 1e-6},
               'small helicopter': {'no requirement': 'na',
                                    'probable': 1e-3,
                                    'remote': 1e-5,
                                    'extremely remote': 1e-7,
                                    'extremely improbable': 1e-9}}

# population schedule
density_categories = {'congested': {'density': 0.006194,
                                    'body strike': {'vert': 0.1, 'horiz': 0.73},
                                    'head strike': {'vert': 0.0375, 'horiz': 0.0375}},
                      'urban': {'density': 0.002973,
                                'body strike': {'vert': 0.0004, 'horiz': 0.0003},
                                'head strike': {'vert': 0.0002, 'horiz': 0.0002}},
                      'suburban': {'density': 0.001042,
                                   'body strike': {'vert': 0.0001, 'horiz': 0.0011},
                                   'head strike': {'vert': 0.0001, 'horiz': 0.0001}},
                      'rural': {'density': 0.0001042,
                                'body strike': {'vert': 0.0000, 'horiz': 0.0001},
                                'head strike': {'vert': 0.000, 'horiz': 0.000}},
                      'remote': {'density': 1.931e-6,
                                 'body strike': {'vert': 0.0000, 'horiz': 0.0000},
                                 'head strike': {'vert': 0.000, 'horiz': 0.000}}}

unsafecost = {'congested': 1000, 'urban': 100, 'suburban': 25, 'rural': 5, 'remote': 1}
propertycost = {'congested': 100000, 'urban': 10000,
                'suburban': 1000, 'rural': 1000, 'remote': 1000}
# safety class schedule
safety_categories = {'catastrophic': {'injuries': 'multiple fatalities',
                                      'safety margins': 'na',
                                      'crew workload': 'na',
                                      'cost': 2000000},
                     'hazardous': {'injuries': 'single fatality and/or multiple serious injuries',
                                   'safety margins': 'large decrease',
                                   'crew workload': 'compromises safety',
                                   'cost': 9600000},
                     'major': {'injuries': 'non-serious injuries',
                               'safety margins': 'significant decrease',
                               'crew workload': 'significant increase',
                               'cost': 2428800},
                     'minor': {'injuries': 'na',
                               'safety margins':
                                   'slight decrease',
                                   'crew workload':
                                       'slight increase',
                                       'cost': 28800},
                     'no effect': {'injuries': 'na',
                                   'safety margins': 'na',
                                   'crew workload': 'na',
                                   'cost': 0}}

hazards = {'VH-1': 'loss of control',
           'VH-2': 'fly-away / non-conformance',
           'VH-3': 'loss of communication',
           'VH-4': 'loss of navigation',
           'VH-5': 'unsuccessful landing',
           'VH-6': 'unintentional flight termination',
           'VH-7': 'collision'}


if __name__ == "__main__":
    import fmdtools.sim.propagate as prop
    import matplotlib.pyplot as plt
    from fmdtools.analyze import show

    mdl = Drone()
    

    
    ec, mdlhist = prop.nominal(mdl)
    phases, modephases = mdlhist.get_modephases()
    an.plot.phases(phases, modephases)

    mdl = Drone()
    app = SampleApproach(mdl,  phases={'move'})
    endclasses, mdlhists = prop.approach(mdl, app, staged=True)
    h = History(nominal=mdlhists.nominal,
                faulty=mdlhists.store_ee_lowcharge_t6p0)
    
    fig, ax = show.trajectories(mdlhists, "dofs.s.x", "dofs.s.y")
    fig, ax = show.trajectories(mdlhists, "dofs.s.x", "dofs.s.y", "dofs.s.z")
    fig, ax = show.trajectories(h, "dofs.s.x", "dofs.s.y", "dofs.s.z")
    
    
    fig, ax = plot_env_with_traj3d(h, mdl)
    fig, ax = plot_env_with_traj(mdlhists, mdl)
    
