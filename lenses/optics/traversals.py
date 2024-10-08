from queue import Queue
from typing import Pattern

from .. import hooks
from .base import Traversal


class EachTraversal(Traversal):
    """A traversal that iterates over its state, focusing everything it
    iterates over. It uses `lenses.hooks.fromiter` to reform the state
    afterwards so it should work with any iterable that function
    supports. Analogous to `iter`.

        >>> from lenses import lens
        >>> state = [1, 2, 3]
        >>> EachTraversal()
        EachTraversal()
        >>> EachTraversal().to_list_of(state)
        [1, 2, 3]
        >>> EachTraversal().over(state, lambda n: n + 1)
        [2, 3, 4]

    For technical reasons, this lens iterates over dictionaries by their
    items and not just their keys.

        >>> state = {'one': 1}
        >>> EachTraversal().to_list_of(state)
        [('one', 1)]
    """

    def __init__(self):
        pass

    def folder(self, state):
        return hooks.to_iter(state)

    def builder(self, state, values):
        return hooks.from_iter(state, values)

    def __repr__(self):
        return "EachTraversal()"


class GetZoomAttrTraversal(Traversal):
    """A traversal that focuses an attribute of an object, though if
    that attribute happens to be a lens it will zoom the lens. This
    is used internally to make lenses that are attributes of objects
    transparent. If you already know whether you are focusing a lens or
    a non-lens you should be explicit and use a ZoomAttrTraversal or a
    GetAttrLens respectively.
    """

    def __init__(self, name):
        from lenses.optics import GetattrLens

        self.name = name
        self._getattr_cache = GetattrLens(name)

    def func(self, f, state):
        attr = getattr(state, self.name)
        try:
            sublens = attr._optic
        except AttributeError:
            sublens = self._getattr_cache
        return sublens.func(f, state)

    def __repr__(self):
        return "GetZoomAttrTraversal({!r})".format(self.name)


class ItemsTraversal(Traversal):
    """A traversal focusing key-value tuples that are the items of a
    dictionary. Analogous to `dict.items`.

        >>> from collections import OrderedDict
        >>> state = OrderedDict([(1, 10), (2, 20)])
        >>> ItemsTraversal()
        ItemsTraversal()
        >>> ItemsTraversal().to_list_of(state)
        [(1, 10), (2, 20)]
        >>> ItemsTraversal().over(state, lambda n: (n[0], n[1] + 1))
        OrderedDict([(1, 11), (2, 21)])
    """

    def __init__(self):
        pass

    def folder(self, state):
        return state.items()

    def builder(self, state, values):
        data = state.copy()
        data.clear()
        data.update(v for v in values if v is not None)
        return data

    def __repr__(self):
        return "ItemsTraversal()"


class RecurTraversal(Traversal):
    """A traversal that recurses through an object focusing everything it
    can find of a particular type. This traversal will probe arbitrarily
    deep into the contents of the state looking for sub-objects. It
    uses some naughty tricks to do this including looking at an object's
    `__dict__` attribute.

    It is somewhat analogous to haskell's uniplate optic.

        >>> RecurTraversal(int)
        RecurTraversal(<... 'int'>)
        >>> data = [[1, 2, 100.0], [3, 'hello', [{}, 4], 5]]
        >>> RecurTraversal(int).to_list_of(data)
        [1, 2, 3, 4, 5]
        >>> class Container(object):
        ...     def __init__(self, contents):
        ...         self.contents = contents
        ...     def __repr__(self):
        ...         return 'Container({!r})'.format(self.contents)
        >>> data = [Container(1), 2, Container(Container(3)), [4, 5]]
        >>> RecurTraversal(int).over(data, lambda n: n+1)
        [Container(2), 3, Container(Container(4)), [5, 6]]
        >>> RecurTraversal(Container).to_list_of(data)
        [Container(1), Container(Container(3))]

    Be careful with this; it can focus things you might not expect.
    """

    def __init__(self, cls):
        self.cls = cls
        self._builder_cache = {}
        if hasattr(cls, "__hash__"):
            self.use_hash = True

    def folder(self, state):
        if isinstance(state, self.cls):
            yield state
        elif self.can_iter(state):
            for substate in hooks.to_iter(state):
                for focus in self.folder(substate):
                    yield focus
        elif hasattr(state, "__dict__"):
            for attr in sorted(state.__dict__):
                substate = getattr(state, attr)
                for focus in self.folder(substate):
                    yield focus


def defolder(self, state, focus_values):
    stack = [state]
    focus_iter = iter(focus_values)

    while stack:
        current_state = stack.pop()

        if isinstance(current_state, self.cls):
            try:
                focus_value = next(focus_iter)
                self.apply_focus(current_state, focus_value)
            except StopIteration:
                raise ValueError("Not enough focus values provided.")
            
        elif self.can_iter(current_state):
            substates = list(hooks.to_iter(current_state))
            stack.extend(reversed(substates))
        elif hasattr(current_state, "__dict__"):
            stack.extend(
                (getattr(current_state, attr) for attr in sorted(current_state.__dict__))
            )

    def folder(self, state):

        substates = Queue()

        if isinstance(state, self.cls):
            yield state
        elif self.can_iter(state):
            for substate in hooks.to_iter(state):
                for focus in self.folder(substate):
                    yield focus
        elif hasattr(state, "__dict__"):
            for attr in sorted(state.__dict__):
                substate = getattr(state, attr)
                for focus in self.folder(substate):
                    yield focus

    def defolder(self, state, values):
        if isinstance(state, self.cls):
            assert len(values) == 1
            state = yield state
        elif self.can_iter(state):
            for substate in hooks.to_iter(state):
                yield from self.defolder(substate)
        elif hasattr(state, "__dict__"):
            for attr in sorted(state.__dict__):
                substate = getattr(state, attr)
                yield from self.folder(substate)


    def builder(self, state, values):
        built_state_cache = {} 
        try:
            _hash = hash(state)
            return built_state_cache[_hash]
        except TypeError:
            _hash = None
        except KeyError:
            pass   
        if isinstance(state, self.cls):
            assert len(values) == 1
            state = values[0]       
        elif self.can_iter(state) or hasattr(state, "__dict__"):
            state = self._build_iterable(state, values)
            new_substates = []
            for substate in hooks.to_iter(state):
                if count := len(list(self.folder(substate))):
                    subvalues, values = values[:count], values[count:]
                    substate = self._builder(substate, subvalues)
                new_substates.append(substate)
            assert not values
            state = hooks.from_iter(state, new_substates)
        elif hasattr(state, "__dict__"):
            for attr, substate in sorted(state.__dict__.items()):
                if count := len(list(self.folder(substate))):
                    subvalues, values = values[:count], values[count:]
                    new_substate = self._builder(substate, subvalues)
                    state = hooks.setattr(state, attr, new_substate)
            assert not values
        if _hash is not None:
            built_state_cache[_hash] = state
        return state

    @staticmethod
    def can_iter(state):
        # characters appear iterable because they are just strings,
        # but if we actually try to iterate over them then we enter
        # infinite recursion
        if isinstance(state, str) and len(state) == 1:
            return False

        from_types = set(hooks.from_iter.registry.keys()) - {object}
        can_from = any(isinstance(state, type_) for type_ in from_types)
        return can_from

    def __repr__(self):
        return "RecurTraversal({!r})".format(self.cls)


class RegexTraversal(Traversal):
    """A traversal that uses a regex to focus parts of a string."""

    def __init__(self, pattern: Pattern, flags: int) -> None:
        self.pattern = pattern
        self.flags = flags

    def folder(self, state):
        import re

        for match in re.finditer(self.pattern, state, flags=self.flags):
            yield match.group(0)

    def builder(self, state, values):
        import re

        iterator = iter(values)
        return re.sub(self.pattern, lambda _: next(iterator), state, flags=self.flags)

    def __repr__(self) -> str:
        return f"RegexTraversal({self.pattern}, flags={self.flags})"


class ZoomAttrTraversal(Traversal):
    """A lens that looks up an attribute on its target and follows it as
    if were a bound `Lens` object. Ignores the state, if any, of the
    lens that is being looked up.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def func(self, f, state):
        optic = getattr(state, self.name)._optic
        return optic.func(f, state)

    def __repr__(self):
        return "ZoomAttrTraversal({!r})".format(self.name)


class ZoomTraversal(Traversal):
    """Follows its state as if it were a bound `Lens` object.

    >>> from lenses import bind
    >>> ZoomTraversal()
    ZoomTraversal()
    >>> state = bind([1, 2])[1]
    >>> ZoomTraversal().view(state)
    2
    >>> ZoomTraversal().set(state, 3)
    [1, 3]
    """

    def __init__(self):
        pass

    def func(self, f, state):
        return state._optic.func(f, state._state)

    def __repr__(self):
        return "ZoomTraversal()"
