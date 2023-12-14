# -*- coding: utf-8 -*-
"""
Description: A module for defining timers for use in Time containers.

Has Classes:
- :class:`Timer`: Class defining timers
"""
from fmdtools.analyze.history import History
from fmdtools.define.object.base import BaseObject


class Timer(BaseObject):
    """
    Class for model timers used in functions (e.g. for conditional faults).

    Attributes
    ----------
    name : str
        timer name
    time : float
        internal timer clock time
    tstep : float
        time to increment at each time-step
    mode : str (standby/ticking/complete)
        the internal state of the timer
    """

    default_track = ('time', 'mode')
    roletypes = []
    rolevars = ['time', 'mode']

    def __init__(self, name=''):
        """
        Initializes the Tymer

        Parameters
        ----------
        name : str
            Name for the timer
        """
        BaseObject.__init__(self, name=name)
        self.name = str(name)
        self.time = 0.0
        self.tstep = -1.0
        self.mode = 'standby'

    def __repr__(self):
        return ('Timer ' + self.name + ': mode= '
                + self.mode + ', time= ' + str(self.time))

    def t(self):
        """Return the time elapsed."""
        return self.time

    def inc(self, tstep=[]):
        """Increment the time elapsed by tstep."""
        if self.time >= 0.0:
            if tstep:
                self.time += tstep
            else:
                self.time += self.tstep
            self.mode = 'ticking'
        if self.time <= 0:
            self.time = 0.0
            self.mode = 'complete'

    def reset(self):
        """Reset the time to zero."""
        self.time = 0.0
        self.mode = 'standby'

    def set_timer(self, time, tstep=-1.0, overwrite='always'):
        """
        Set timer to a given time.

        Parameters
        ----------
        time : float
            set time to count down in the timer
        tstep : float (default -1.0)
            time to increment the timer at each time-step
        overwrite : str
            whether/how to overwrite the previous time
            'always' (default) sets the time to the given time
            'if_more' only overwrites the old time if the new time is greater
            'if_less' only overwrites the old time if the new time is less
            'never' doesn't overwrite an existing timer unless it has reached 0.0
            'increment' increments the previous time by the new time
        """
        if overwrite == 'always':
            self.time = time
        elif overwrite == 'if_more' and self.time < time:
            self.time = time
        elif overwrite == 'if_less' and self.time > time:
            self.time = time
        elif overwrite == 'never' and self.time == 0.0:
            self.time = time
        elif overwrite == 'increment':
            self.time += time
        self.tstep = tstep
        self.mode = 'set'

    def indicate_standby(self):
        """Indicate if the timer is in standby (time not set)."""
        return self.mode == 'standby'

    def indicate_ticking(self):
        """Indictate if the timer is ticking (time is incrementing)."""
        return self.mode == 'ticking'

    def indicate_complete(self):
        """Indicate if the timer is complete (after time is done incrementing)."""
        return self.mode == 'complete'

    def indicate_set(self):
        """Indicate if the timer is set (before time increments)."""
        return self.mode == 'set'

    def copy(self):
        """Copy the Timer."""
        cop = self.__class__(self.name)
        cop.time = self.time
        cop.mode = self.mode
        cop.dt = self.dt
        return cop

if __name__ == "__main__":
    import doctest
    doctest.testmod(verbose=True)


