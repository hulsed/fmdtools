# -*- coding: utf-8 -*-
"""
Description: A module for methods used commonly in model definition constructs.

Functions contained in this module:

- :func:`get_var`:Gets the variable value of the object
- :func:`set_var`:Sets variable of the object to a given value
- :func:`is_iter`: Checks whether a data type should be interpreted as an iterable or
not.
- :func:`check_pickleability`:Checks to see which attributes of an object will pickle
  (and thus parallelize)"
- :func:`init_obj_attr`:Initializes attributes to a given object
- :func:`init_obj_dict`: Create a dict in an object for the attribute 'spec'.
- :func:`get_obj_track`:Gets tracking params for a given object (block, model, etc)
- :func:`t_key`:Used to generate keys for a given (float) time that is queryable as
  an attribute of an object/dict

"""
from collections.abc import Iterable
import dill
import pickle
import time
from recordclass import asdict, dataobject


def get_var(obj, var):
    """
    Gets the variable value of the object

    Parameters
    ----------
    var : str/list
        list specifying the attribute (or sub-attribute of the object
    Returns
    -------
    var_value: any
        value of the variable
    """
    if type(var) == str:
        var_s = var.split(".")
    else:
        var_s = var
        var = ".".join(var_s)
    if len(var_s) == 1:
        k = var_s[0]
        if type(obj) == dict or (hasattr(obj, 'keys') and hasattr(obj, 'values')):
            val = obj.get(k, None)
        elif type(obj) in {tuple, list} and k.isnumeric():
            val = obj[int(k)]
        else:
            val = getattr(obj, k)
        if hasattr(val, 'value'):
            return val.value
        else:
            return val
    else:
        if type(obj) == dict:
            if var_s[0] in obj:
                return get_var(obj[var_s[0]], var_s[1:])
            elif var in obj:
                return obj[var]
            else:
                raise Exception(var + "not in " + str(obj))
        elif (hasattr(obj, 'keys') and hasattr(obj, 'values')):
            if var_s[0] in obj.keys:
                return get_var(obj.get(var_s[0]), var_s[1:])
            elif var in obj.keys:
                return obj.get(var)
            else:
                raise Exception(var + "not in " + str(obj))
        else:
            return get_var(getattr(obj, var_s[0]), var_s[1:])


def set_var(obj, var, val):
    """
    Sets variable of the object to a given value

    Parameters
    ----------
    var : list/tuple of strings
        list of nested attributes
    val : attr
        attribute to set the value to

    Returns
    -------
    flowdict : dict
        dict of flows indexed by flownames
    """
    if type(var) == str:
        var = var.split(".")
    # if not attrgetter(".".join(var))(self):
    #    raise Exception("does not exist: "+str(var))

    if len(var) == 1:
        if type(obj) == dict:
            obj[var[0]] = val
        else:
            setattr(obj, var[0], val)
    else:
        if type(obj) == dict:
            set_var(obj[var[0]], var[1:], val)
        else:
            set_var(getattr(obj, var[0]), var[1:], val)


def nest_dict(dic, levels=float('inf'), separator="."):
    """
    Nest a dictionary a certain number of levels by separator.

    Parameters
    ----------
    dict : dict
        Dictionary to nest. e.g. {'a.b': 1.0}
    levels : int, optional
        DESCRIPTION. The default is float('inf').
    separator : str
        Saparator to nest by. The default is "."

    Returns
    -------
    newhist : dict
        Nested dictionary. e.g. {'a': {'b': 1.0}}
    """
    newhist = dic.__class__()
    key_options = set([h.split(separator)[0] for h in dic.keys()])
    for key in key_options:
        if key in dic:
            newhist[key] =dic[key]
        else:
            subdict = {histkey[len(key)+1:]: val
                       for histkey, val in dic.items()
                       if histkey.startswith(key+separator)}
            subhist = dic.__class__(**subdict)
            lev = levels-1
            if lev > 0:
                newhist[key] = nest_dict(subhist, levels=lev, separator=separator)
            else:
                newhist[key] = subhist
    return newhist


def set_arg_as_type(true_type, new_arg):
    """
    Set a given argument as the type true_type.

    Parameters
    ----------
    true_type : class/type
        Class/type to set to
    new_arg : value
        Value to set as.

    Returns
    -------
    new_arg : value
        Value with correct type (if possible).
    """
    arg_type = type(new_arg)
    if arg_type != true_type:
        if arg_type == dict or issubclass(arg_type, dataobject):
            if true_type == tuple:
                new_arg = true_type(new_arg.values())
            else:
                new_arg = true_type(**new_arg)
        else:
            new_arg = true_type(new_arg)
    return new_arg


def is_iter(data):
    """
    Check whether a data type should be interpreted as an iterable or not.

    Returned as a single value or tuple/array.
    """
    if isinstance(data, Iterable) and type(data) != str:
        return True
    else:
        return False


def check_pickleability(obj, verbose=True, try_pick=False, pause=0.2):
    """Check to see which attributes of an object will pickle (and parallelize)."""
    from pickle import PicklingError
    unpickleable = []
    try:
        itera = vars(obj)
    except:
        itera = {a: getattr(obj, a) for a in obj.__slots__}
    for name, attribute in itera.items():
        print(name)
        time.sleep(pause)
        try:
            if not dill.pickles(attribute):
                unpickleable = unpickleable + [name]
        except ValueError as e:
            raise ValueError("Problem in " + name +
                             " with attribute " + str(attribute)) from e
        if try_pick:
            try:
                a = pickle.dumps(attribute)
                b = pickle.loads(a)
            except:
                raise Exception(obj.name + " will not pickle")
    if try_pick:
        try:
            a = pickle.dumps(obj)
            b = pickle.loads(a)
        except PicklingError as e:
            raise Exception(obj.name + " will not pickle") from e
    if verbose:
        if unpickleable:
            print("The following attributes will not pickle: " + str(unpickleable))
        else:
            print("The object is pickleable")
    return unpickleable


def init_obj_dict(obj, spec, name_end="s", set_attr=False):
    """
    Create a dict for the attribute 'spec'.

    Works by finding all attributes from the obj's parameter with the name 'spec' in
    them and adding them to the dict. Adds the dict to the object.

    Parameters
    ----------
    obj : object
        Object with _spec_ attributes
    spec : str
        Name of the attributes to initialize
    set_attr : bool
        Whether to also add the individual attributes attr to the obj
    sub_obj : str
        Sub-object to form the object from (e.g., 'p' if defined in a parameter).
        Default is '', which gets from obj.
    """
    spec_len = len(spec) + 1
    specs = {p[spec_len:]: obj.p[p] for p in obj.p.__fields__ if spec in p}
    specname = spec + name_end
    setattr(obj, specname, specs)
    if set_attr:
        for s_name in specs:
            setattr(obj, s_name, specs[s_name])


def eq_units(rateunit, timeunit):
    """
    Find conversion factor for from rateunit (str) to timeunit (str).

    Options for units are: 'sec', 'min', 'hr', 'day', 'wk', 'month', and 'year'.
    """
    factors = {'sec': 1,
               'min': 60,
               'hr': 3600,
               'day': 86400,
               'wk': 604800,
               'month': 2629746,
               'year': 31556952}
    return factors[timeunit]/factors[rateunit]


def t_key(time):
    """Used to generate keys for a given (float) time that is queryable
    as an attribute of an object/dict, e.g. endresults.t10p0, the result at time
    t=10.0"""
    return 't'+'p'.join(str(time).split('.'))


class BaseObject(object):
    __slots__ = ('name', 'containers', 'indicators')

    def __init__(self, name='', **kwargs):
        if not name:
            self.name = self.__class__.__name__.lower()
        else:
            self.name = name
        self.init_indicators()
        self.init_roles('container', **kwargs)

    def init_roles(self, roletype, **kwargs):
        """
        Initialize the roles for a given object.

        Roles defined using container_x in its class variables for the attribute x.

        Object is instantiated with the attribute x corresponding to output of container_x.

        Parameters
        ----------
        *roles : str
            Roles to initialize. If none provided, initializes all.
        **kwargs : dict
            Dictionary arguments (or already instantiated objects) to use for the
            attributes.
        """
        container_collection = roletype + 's'
        roles = tuple([at[len(roletype)+1:]
                       for at in dir(self) if at.startswith(roletype+'_')])
        setattr(self, container_collection, roles)

        if not roles:
            roles = getattr(self, container_collection)

        for rolename in roles:
            container_initializer = getattr(self, roletype+'_'+rolename)
            if rolename in kwargs:
                container_args = kwargs[rolename]
                if type(container_args) != dict:
                    container_args = asdict(container_args)
            else:
                container_args = {}
            container = container_initializer(**container_args)
            container.check_role(rolename)
            setattr(self, rolename, container)


    def init_indicators(self):
        self.indicators = tuple([at[9:] for at in dir(self)
                                 if at.startswith('indicate_')])

    def get_indicators(self):
        """
        Gets the names of the indicators

        Returns
        -------
        indicators : dict
            dict of indicator names and their associated method handles.
        """
        return {i: getattr(self, 'indicate_'+i) for i in self.indicators}

    def return_true_indicators(self, time):
        """
        Get list of indicators.

        Parameters
        ----------
        time : float
            Time to execute the indicator method at.

        Returns
        -------
        list
            List of inticators that return true at time

        """
        return [f for f, ind in self.get_indicators().items() if ind(time)]

    def get_track(obj, track, all_possible=()):
        """
        Get tracking params for a given object (block, model, etc).

        Parameters
        ----------
        track : track
            str/tuple. Attributes to track.
            'all' tracks all fields
            'default' tracks fields defined in default_track for the dataobject
            'none' tracks none of the fields

        Returns
        -------
        track : tuple
            fields to track
        """
        if track == 'default':
            track = obj.default_track
        if track == 'all':
            track = all_possible
        elif track in ['none', False]:
            track = ()
        elif type(track) == str:
            track = (track,)
        return track


