# -*- coding: utf-8 -*-
"""
Description: Module for analyzing phases and time-based sampling schemes.

Has classes:
- :class:`PhaseMap`: A mapping of phases to times.

And functions:

- :func:`from_hist`: Creates dict of PhaseMaps based on mode progression in history.
- :func:`phaseplot`: Plots the progression of phases over time.
- :func:`samplemetric
- :func:`samplemetric`: plots a metric for a single fault sampled by a SampleApproach
  over time with rates
- :func:`samplemetrics`: plots a metric for a set of faults sampled by a SampleApproach
  over time with rates on separate plots
- :func:`metricovertime`: plots the total metric/explected metric of a set of faults
  sampled by a SampleApproach over time
- :func:`find_overlap_n`: Find overlap between given intervals.
- :func:`gen_interval_times`: Creates times in a given interval.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import matplotlib.colors as mcolors
from fmdtools.analyze.tabulate import metricovertime as metric_table
from ordered_set import OrderedSet

plt.rcParams['pdf.fonttype'] = 42


class PhaseMap(object):
    """
    Mapping of phases to times used to create scenario samples.

    Phases and modephases may be generated from Result.get_phases.

    Parameters
    ----------
    phases : dict
        Phases the mode will be injected during. Used to determine opportunity
        factor defined by the dict in fault.phases.
        Has structure {'phase1': [starttime, endtime]}. The default is {}.
        May also provide tuple with structure (('phase1', starttime, endtime))
    modephases : dict, optional
        Modes that the phases occur in. Used to determine opportunity vector defined
        by the dict in fault.phases (if .phases maps to modes of occurence an not
        phases).
        Has structure {'on': {'on1', 'on2', 'on3'}}. The default is {}.
    dt: float
        Timestep defining phases.
    """

    def __init__(self, phases, modephases={}, dt=1.0):
        if type(phases) == tuple:
            phases = {ph[0]: [ph[1], ph[2]] for ph in phases}
        self.phases = phases
        self.modephases = modephases
        self.dt = dt

    def __repr__(self):
        return 'PhaseMap(' + str(self.phases) + ', ' + str(self.modephases) + ')'

    def find_phase(self, time, dt=1.0):
        """
        Find the phase that a time occurs in.

        Parameters
        ----------
        time : float
            Occurence time.

        Returns
        -------
        phase : str
            Name of the phase time occurs in.
        """
        for phase, times in self.phases.items():
            if times[0] <= time < times[1]+dt:
                return phase
        raise Exception("time "+str(time)+" not in phases: "+str(self.phases))

    def find_modephase(self, phase):
        """
        Find the mode in modephases that a given phase occurs in.

        Parameters
        ----------
        phase : str
            Name of the phase (e.g., 'on1').

        Returns
        -------
        mode : str
            Name of the corresponding mode (e.g., 'on').

        Examples
        --------
        >>> pm = PhaseMap({}, {"on": {"on0", "on1", "on2"}})
        >>> pm.find_modephase("on1")
        'on'
        """
        for mode, mode_phases in self.modephases.items():
            if phase in mode_phases:
                return mode
        raise Exception("Phase "+phase+" not in modephases: "+str(self.modephases))

    def find_base_phase(self, time):
        """
        Find the phase or modephase (if provided) that the time occurs in.

        Parameters
        ----------
        time : float
            Time to check.

        Returns
        -------
        phase : str
            Phase or modephase the time occurs in.
        """
        phase = self.find_phase(time)
        if self.modephases:
            phase = self.find_modephase(phase)
        return phase

    def calc_samples_in_phases(self, *times):
        """
        Calculate the number of times the provided times show up in phases/modephases.

        Parameters
        ----------
        *times : float
            Times to check

        Returns
        -------
        phase_times : TYPE
            DESCRIPTION.

        Examples
        --------
        >>> pm = PhaseMap(phases={'on':[0, 3], 'off': [4, 5]})
        >>> pm.calc_samples_in_phases(1,2,3,4,5)
        {'on': 3, 'off': 2}
        >>> pm = PhaseMap({'on':[0, 3], 'off': [4, 5]}, {'oper': {'on', 'off'}})
        >>> pm.calc_samples_in_phases(1,2,3,4,5)
        {'oper': 5}
        """
        if self.modephases:
            phase_times = {ph: 0 for ph in self.modephases}
        else:
            phase_times = {ph: 0 for ph in self.phases}
        for time in times:
            phase = self.find_phase(time)
            if self.modephases:
                phase = self.find_modephase(phase)
            phase_times[phase] += 1
        return phase_times

    def calc_phase_time(self, phase):
        """
        Calculate the length of a phase.

        Parameters
        ----------
        phase : str
            phase to calculate.
        phases : dict
            dict of phases and time intervals.
        dt : float, optional
            Timestep length. The default is 1.0.

        Returns
        -------
        phase_time : float
            Time of the phase


        Examples
        --------
        >>> pm = PhaseMap({"on": [0, 4], "off": [5, 10]})
        >>> pm.calc_phase_time("on")
        5.0
        """
        phasetimes = self.phases[phase]
        phase_time = phasetimes[1] - phasetimes[0] + self.dt
        return phase_time

    def calc_modephase_time(self, modephase):
        """
        Calculate the amount of time in a mode, given that mode maps to multiple phases.

        Parameters
        ----------
        modephase : str
            Name of the mode to check.
        phases : dict
            Dict mapping phases to times.
        modephases : dict
            Dict mapping modes to phases
        dt : float, optional
            Timestep. The default is 1.0.

        Returns
        -------
        modephase_time : float
            Amount of time in the modephase

        Examples
        --------
        >>> pm = PhaseMap({"on1": [0, 1], "on2": [2, 3]}, {"on": {"on1", "on2"}})
        >>> pm.calc_modephase_time("on")
        4.0
        """
        modephase_time = sum([self.calc_phase_time(mode_phase)
                              for mode_phase in self.modephases[modephase]])
        return modephase_time

    def calc_scen_exposure_time(self, time):
        """
        Calculate the time for the phase/modephase at the given time.

        Parameters
        ----------
        time : float
            Time within the phase.

        Returns
        -------
        exposure_time : float
            Exposure time of the given phasemap.
        """
        phase = self.find_phase(time)
        if self.modephases:
            phase = self.find_modephase(phase)
            return self.calc_modephase_time(phase)
        else:
            return self.calc_phase_time(phase)

    def get_phase_times(self, phase):
        """
        Get the set of discrete times in the interval for a phase.

        Parameters
        ----------
        phase : str
            Name of a phase in phases or modephases.

        Returns
        -------
        all_times : list
            List of times corresponding to the phase

        Examples
        --------
        >>> pm = PhaseMap({"on1": [0, 1], "on2": [2, 3]}, {"on": {"on1", "on2"}})
        >>> pm.get_phase_times('on1')
        [0.0, 1.0]
        >>> pm.get_phase_times('on2')
        [2.0, 3.0]
        >>> pm.get_phase_times('on')
        [0.0, 1.0, 2.0, 3.0]
        """
        if phase in self.modephases:
            phases = self.modephases[phase]
            intervals = [self.phases[ph] for ph in phases]
        elif phase in self.phases:
            intervals = [self.phases[phase]]
        int_times = [gen_interval_times(i, self.dt) for i in intervals]
        all_times = list(set(np.concatenate(int_times)))
        all_times.sort()
        return all_times

    def get_sample_times(self, *phases_to_sample):
        """
        Get the times to sample for the given phases.

        Parameters
        ----------
        *phases_to_sample : str
            Phases to sample. If none are provided, the full set of phases or modephases
            is used.

        Returns
        -------
        sampletimes : dict
            dict of times to sample with structure {'phase1': [t0, t1, t2], ...}

        Examples
        --------
        >>> pm = PhaseMap({"on1": [0, 4], "on2": [5, 6]}, {"on": {"on1", "on2"}})
        >>> pm.get_sample_times("on1")
        {'on1': [0.0, 1.0, 2.0, 3.0, 4.0]}
        >>> pm.get_sample_times("on")
        {'on': [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}
        >>> pm.get_sample_times("on1", "on2")
        {'on1': [0.0, 1.0, 2.0, 3.0, 4.0], 'on2': [5.0, 6.0]}
        """
        if not phases_to_sample:
            if self.modephases:
                phases_to_sample = tuple(self.modephases)
            elif self.phases:
                phases_to_sample = tuple(self.phases)
        sampletimes = {}
        for phase in phases_to_sample:
            sampletimes[phase] = self.get_phase_times(phase)
        return sampletimes


def from_hist(hist, fxn_modephases = 'all'):
    """
    Identify the phases of operation for the system based on its modes.

    These phases and modephases are then be used to define a dict of PhaseMaps.

    Parameters
    ----------
    hist : History
        History of states with mode information in them
    fxn_modephases : list
        Functions to associate modephase information from
        (rather than just phase information)

    Returns
    -------
    phasemaps : dict
        Dictionary of distict phases that the system functions pass through,
        of the form: {'fxn': PhaseMap} where each phase is defined by its
        corresponding mode in the modelhist.
        Phases are numbered mode, mode1, mode2 for multiple modes and given a
        corresponding phasemap {mode: {mode, mode1, mode2}} mapping modes to
        phases for future sampling.
    """
    modephasemaps = {}
    times = hist['time']
    modehists = hist.get_values('m.mode')
    for k, modehist in modehists.items():
        if type(k) == str:
            k = k.split(".")
        fxn = k[k.index('m')-1]
        if len(modehist) != 0:
            modes = OrderedSet(modehist)
            modephases = dict.fromkeys(modes)
            phases_unsorted = dict()
            for mode in modes:
                modeinds = [ind for ind, m in enumerate(modehist) if m == mode]
                startind = modeinds[0]
                phasenum = 0
                phaseid = mode
                modephases[mode] = set()
                for i, ind in enumerate(modeinds):
                    if ind+1 not in modeinds:
                        phases_unsorted[phaseid] = [times[startind], times[ind]]
                        modephases[mode].add(phaseid)
                        if i != len(modeinds)-1:
                            startind = modeinds[i+1]
                            phasenum += 1
                            phaseid = mode+str(phasenum)
            phases = dict(sorted(phases_unsorted.items(),
                                 key=lambda item: item[1][0]))
            if fxn_modephases == 'all' or fxn in fxn_modephases:
                mph = modephases
            else:
                mph = {}
            modephasemaps[fxn] = PhaseMap(phases=phases, modephases=mph)
    return modephasemaps


def phaseplot(phasemaps, modephases=[], mdl=[], dt=1.0, singleplot=True,
              phase_ticks='both', figsize="default", v_padding=0.5, title_padding=-0.05,
              title="Progression of model through operational phases"):
    """
    Plots the phases of operation that the model progresses through.

    Parameters
    ----------
    mdlphases : dict or PhaseMap
        Dict of phasemaps that the functions of the model progresses through
        (e.g. from phases.from_hist).
    modephases : dict, optional
        dictionary that maps the phases to operational modes, if it is desired to track
        the progression through modes
    mdl : Model, optional
        model, if it is desired to additionally plot the phases of the model with the
        function phases
    singleplot : bool, optional
        Whether the functions' progressions through phases are plotted on the same plot
        or on different plots.
        The default is True.
    phase_ticks : 'std'/'phases'/'both'
        x-ticks to use (standard, at the edge of phases, or both). Default is 'both'
    figsize : tuple (float,float)
        x-y size for the figure. The default is 'default', which dymanically gives 2 for
        each row
    v_padding : float
        vertical padding between subplots as a fraction of axis height
    title_padding : float
        padding for title as a fraction of figure height
    Returns
    -------
    fig/figs : Figure or list of Figures
        Matplotlib figures to edit/use.

    """
    if mdl:
        phasemaps["Model"] = PhaseMap(mdl.phases)
        dt = mdl.tstep

    if isinstance(phasemaps, PhaseMap):
        phasemaps = {'': phasemaps}
    elif not isinstance(phasemaps, dict):
        raise Exception("Phasemaps not a dict or PhaseMap")

    if singleplot:
        num_plots = len(phasemaps)
        if figsize == 'default':
            figsize = (4, 2*num_plots)
        fig = plt.figure(figsize=figsize)
    else:
        if figsize == 'default':
            figsize = (4, 4)
        figs = []

    for i, (fxn, phasemap) in enumerate(phasemaps.items()):
        if singleplot:
            ax = plt.subplot(num_plots, 1, i+1, label=fxn)
        else:
            fig, ax = plt.subplots(figsize=figsize)
        modephases = phasemap.modephases
        phases = phasemap.phases

        if modephases:
            mode_nums = {ph: i for i, (k, v) in enumerate(modephases.items())
                         for ph in v}
            ylabels = list(modephases.keys())
        else:
            mode_nums = {ph: i for i, ph in enumerate(phases)}
            ylabels = list(mode_nums.keys())

        phaseboxes = [((v[0]-.5*dt, mode_nums[k]-.4),
                       (v[0]-.5*dt, mode_nums[k]+.4),
                       (v[1]+.5*dt, mode_nums[k]+.4),
                       (v[1]+.5*dt, mode_nums[k]-.4)) for k, v in phases.items()]
        color_options = list(mcolors.TABLEAU_COLORS.keys())[0:len(ylabels)]
        colors = [color_options[mode_nums[phase]] for phase in phases]
        bars = PolyCollection(phaseboxes, facecolors=colors)

        ax.add_collection(bars)
        ax.autoscale()

        ax.set_yticks(list(set(mode_nums.values())))
        ax.set_yticklabels(ylabels)

        times = [0]+[v[1] for k, v in phases.items()]
        if phase_ticks == 'both':
            ax.set_xticks(list(set(list(ax.get_xticks())+times)))
        elif phase_ticks == 'phases':
            ax.set_xticks(times)
        ax.set_xlim(times[0], times[-1])
        plt.grid(which='both', axis='x')
        if singleplot:
            plt.title(fxn)
        else:
            plt.title(title)
            figs.append(fig)
    if singleplot:
        plt.suptitle(title, y=1.0+title_padding)
        plt.subplots_adjust(hspace=v_padding)
        return fig
    else:
        return figs


def samplemetric(app, endclasses, fxnmode,
                 samptype='std', title="", metric='cost', ylims=None):
    """
    Plots the sample metric and rate of a given fault over the injection times defined
    in the app sampleapproach

    (note: not currently compatible with joint fault modes)

    Parameters
    ----------
    app : sampleapproach
        Sample approach defining the underlying samples to take and probability model of
        the list of scenarios.
    endclasses : Result
        A Result with the end classification of each fault (metrics, etc)
    fxnmode : tuple
        tuple (or tuple of tuples) with structure ('function name', 'mode name')
        defining the fault mode
    metric : str
        Metric to plot. The default is 'cost'
    samptype : str, optional
        The type of sample approach used.
        Options include:

            - 'std' for a single point for each interval
            - 'quadrature' for a set of points with weights defined by a quadrature
    """
    associated_scens = []
    for phasetup in app.mode_phase_map[fxnmode]:
        associated_scens = associated_scens + app.scenids.get((fxnmode, phasetup), [])
    associated_scens = list(set(associated_scens))
    costs = np.array([endclasses.get(scen).endclass[metric]
                     for scen in associated_scens])

    times = np.array([[a.time for a in app.scenlist if a.name == scen][0]
                      for scen in associated_scens])
    timesort = np.argsort(times)
    times = times[timesort]
    costs = costs[timesort]
    a = 1
    tPlot, axes = plt.subplots(2, 1, sharey=False, gridspec_kw={
                               'height_ratios': [3, 1]})

    phasetimes_start = []
    phasetimes_end = []
    ratesvect = []
    phaselabels = []
    for phase, ptimes in app.mode_phase_map[fxnmode].items():
        if type(ptimes[0]) == list:
            phasetimes_start += [t[0] for t in ptimes]
            phasetimes_end += [t[1] for t in ptimes]
            ratesvect += [app.rates_timeless[fxnmode][phase] for t in ptimes] * 2
            phaselabels += [phase[1] for t in ptimes]
        else:
            phasetimes_start.append(ptimes[0])
            phasetimes_end.append(ptimes[1])
            ratesvect = ratesvect + [app.rates_timeless[fxnmode][phase]]*2
            phaselabels.append(phase[1])
    ratetimes = []
    phaselocs = []
    for (ind, phasetime) in enumerate(phasetimes_start):
        axes[0].axvline(phasetime, color="black")
        phaselocs= phaselocs + [(phasetimes_end[ind] - phasetimes_start[ind])/2 + phasetimes_start[ind]]

        axes[1].axvline(phasetime, color="black")
        ratetimes = ratetimes + [phasetimes_start[ind]] + [phasetimes_end[ind]]
        # axes[1].text(middletime, 0.5*max(rates),  list(app.phases.keys())[ind], ha='center', backgroundcolor="white")
    # rate plots
    axes[1].set_xticks(phaselocs)
    axes[1].set_xticklabels(phaselabels)

    sorty = np.argsort(phasetimes_start)
    phasetimes_start = np.array(phasetimes_start)[sorty]
    phasetimes_end = np.array(phasetimes_end)[sorty]
    sortx = np.argsort(ratetimes)
    axes[1].plot(np.array(ratetimes)[sortx], np.array(ratesvect)[sortx])
    axes[1].set_xlim(phasetimes_start[0], phasetimes_end[-1])
    axes[1].set_ylim(0, np.max(ratesvect)*1.2)
    axes[1].set_ylabel("Rate")
    axes[1].set_xlabel("Time ("+str(app.units)+")")
    axes[1].grid()
    #cost plots
    axes[0].set_xlim(phasetimes_start[0], phasetimes_end[-1])
    if not ylims:
        ylims = [min(1.2*np.min(costs), -1e-5), max(1.2*np.max(costs), 1e-5)]
    axes[0].set_ylim(*ylims)
    if samptype == 'fullint':
        axes[0].plot(times, costs, label=metric)
    else:
        if samptype == 'quadrature':
            sizes = 1000 * np.array([weight if weight != 1 / len(timeweights) else 0.0
                                    for (phasetype, phase), timeweights in app.weights[fxnmode].items() if timeweights
                                    for time, weight in timeweights.items() if time in times])
            axes[0].scatter(times, costs,s=sizes, label=metric, alpha=0.5)
        axes[0].stem(times, costs, label=metric, markerfmt=",", use_line_collection=True)

    axes[0].set_ylabel(metric)
    axes[0].grid()
    if title:
        axes[0].set_title(title)
    elif type(fxnmode[0]) == tuple:
        axes[0].set_title(metric+" function of "+str(fxnmode)+" over time")
    else:
        axes[0].set_title(metric+" function of "+fxnmode[0] +
                          ": "+fxnmode[1]+" over time")
    # plt.subplot_adjust()
    plt.tight_layout()


def samplemetrics(app, endclasses, joint=False, title="", metric='cost'):
    """
    Plots the costs and rates of a set of faults injected over time according to the
    approach app.

    Parameters
    ----------
    app : sampleapproach
        The sample approach used to run the list of faults
    endclasses : Result
        Results over the scenarios defined in app.
    joint : bool, optional
        Whether to include joint fault scenarios. The default is False.
    title : str
        Optional title.
    metric : str
        Metric to plot. The default is 'cost'
    """
    for fxnmode in app.list_modes(joint):
        if any([True for (fm, phase), val in app.sampparams.items()
                if val['samp'] == 'fullint' and fm == fxnmode]):
            st = 'fullint'
        elif any([True for (fm, phase), val in app.sampparams.items()
                  if val['samp'] == 'quadrature' and fm == fxnmode]):
            st = 'quadrature'
        else:
            st = 'std'
        samplemetric(app, endclasses, fxnmode, samptype=st, title="", metric=metric)


def metricovertime(endclasses, app, metric='cost', metrictype='expected cost'):
    """
    Plots the total cost or total expected cost of faults over time.

    Parameters
    ----------
    endclasses : Result
        Result with metrics for each injected scenario over the approach app
        (e.g. from run_approach())
    app : sampleapproach
        sample approach used to generate the list of scenarios
    metric : str
        metric to plot over time. Default is 'cost'
    metrictype : str, optional
        type of metric to plot (e.g, 'cost', 'expected cost' or 'rate').
        The default is 'expected cost'.
    Returns
    -------
    figure: matplotlib figure
    """
    costovertime = metric_table(endclasses, app, metric=metric)
    plt.plot(list(costovertime.index), costovertime[metrictype])
    plt.title('Total '+metrictype+' of all faults over time.')
    plt.ylabel(metrictype)
    plt.xlabel("Time ("+str(app.units)+")")
    plt.grid()
    return plt.gcf()


def find_overlap_n(intervals):
    """
    Find the overlap between given intervals.

    Used to sample joint fault modes with different (potentially overlapping) phases
    """
    try:
        joined_times = {}
        intervals_times = []
        for i, interval in enumerate(intervals):
            if type(interval[0]) in [float, int]:
                interval = [interval]
            possible_times = set()
            possible_times.update(*[{*np.arange(i[0], i[-1]+1)} for i in interval])
            if i == 0:
                joined_times = possible_times
            else:
                joined_times = joined_times.intersection(possible_times)
            intervals_times.append(len(possible_times))
        if not joined_times:
            return [], intervals_times
        else:
            return [*np.sort([*joined_times])], intervals_times
    except IndexError:
        if all(intervals[0] == i for i in intervals):
            return intervals[0]
        else:
            return 0

def gen_interval_times(interval, dt):
    """Generate the times in a given interval given the timestep dt."""
    return np.arange(interval[0], interval[-1] + dt, dt)


if __name__ == "__main__":
    import doctest
    doctest.testmod(verbose=True)
