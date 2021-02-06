from dataclasses import dataclass
import sys
import typing as tp
from copy import copy
from enum import Enum
from functools import total_ordering

import jax
import jax.numpy as jnp
import jax.tree_util
import numpy as np


if sys.version_info >= (3, 8):
    from typing import Protocol, runtime_checkable
else:
    from typing_extensions import Protocol, runtime_checkable

EPSILON = 1e-7


class Mode(int, Enum):
    none = 0
    pred = 1
    test = 2
    train = 3


class TrivialPytree:
    def tree_flatten(self):
        return tuple(vars(self).values()), None

    @classmethod
    def tree_unflatten(cls, _aux_data, children):
        return cls(*children)


class Empty:
    pass


EMPTY = Empty()


@jax.tree_util.register_pytree_node_class
class RNGSeq(TrivialPytree):
    key: jnp.ndarray

    def __init__(self, key: tp.Union[int, jnp.ndarray]):
        self.key = (
            jax.random.PRNGKey(key) if isinstance(key, int) or key.shape == () else key
        )

    def next(self) -> jnp.ndarray:
        self.key = jax.random.split(self.key, 1)[0]
        return self.key

    def __repr__(self) -> str:
        return f"RNGSeq(key={self.key})"


T = tp.TypeVar("T")
Container = tp.Union[
    T,
    tp.Tuple["Container", ...],
    tp.Dict[str, "Container"],
]
ArrayHolder = tp.Union[Container[np.ndarray], np.ndarray]

IndexLike = tp.Union[str, int, tp.Iterable[tp.Union[str, int]]]

Shape = tp.Sequence[int]
ShapeLike = tp.Union[int, Shape]
FloatLike = tp.Union[float, np.ndarray]
DType = tp.Any
ParamName = str

Params = tp.Mapping[str, tp.Mapping[ParamName, np.ndarray]]
State = tp.Mapping[str, tp.Mapping[str, np.ndarray]]
PadFn = tp.Callable[[int], tp.Tuple[int, int]]
PadFnOrFns = tp.Union[PadFn, tp.Sequence[PadFn]]
PRNGKey = np.ndarray
Parameters = tp.Dict[str, tp.Any]
ParameterCollection = tp.Dict[str, Parameters]
Logs = tp.Dict[str, tp.Union[np.ndarray, float]]
Index = tp.Union[int, str]
Path = tp.Tuple[Index, ...]
Grads = tp.Any
RNG = tp.Union[RNGSeq, np.ndarray]
Scalar = tp.Union[np.ndarray, float, int]
SummaryModule = tp.Any
SummaryValue = tp.Any

NetParams = tp.Any
NetStates = tp.Any
ModuleParams = tp.Any
ModuleStates = tp.Any
MetricsStates = tp.Any
OptimizerStates = tp.Any
OptimizerStates = tp.Any
Grads = tp.Any
Pytree = tp.Any


@jax.tree_util.register_pytree_node_class
class Summary(tp.NamedTuple):
    path: Path
    module: tp.Optional[SummaryModule]
    value: SummaryValue

    def tree_flatten(self):
        return ((self.value,), (self.path, self.module))

    @classmethod
    def tree_unflatten(cls, aux_data, children):
        (value,) = children
        path, module = aux_data

        return cls(path, module, value)


Summaries = tp.List[Summary]


@jax.tree_util.register_pytree_node_class
class SummaryTableEntry(tp.NamedTuple):
    path: str
    module_type_name: str
    output_value: Pytree
    trainable_params_count: int
    trainable_params_size: int
    non_trainable_params_count: int
    non_trainable_params_size: int

    @classmethod
    def totals_entry(
        cls,
        trainable_params_count: int,
        trainable_params_size: int,
        non_trainable_params_count: int,
        non_trainable_params_size: int,
    ):
        return cls(
            path="",
            module_type_name="",
            output_value=None,
            trainable_params_count=trainable_params_count,
            trainable_params_size=trainable_params_size,
            non_trainable_params_count=non_trainable_params_count,
            non_trainable_params_size=non_trainable_params_size,
        )

    def tree_flatten(self):
        return (
            (self.output_value,),
            (
                self.path,
                self.module_type_name,
                self.trainable_params_count,
                self.trainable_params_size,
                self.non_trainable_params_count,
                self.non_trainable_params_size,
            ),
        )

    @classmethod
    def tree_unflatten(cls, aux_data, children):
        (
            path,
            module_type_name,
            trainable_params_count,
            trainable_params_size,
            non_trainable_params_count,
            non_trainable_params_size,
        ) = aux_data
        (output_value,) = children

        return cls(
            path=path,
            module_type_name=module_type_name,
            output_value=output_value,
            trainable_params_count=trainable_params_count,
            trainable_params_size=trainable_params_size,
            non_trainable_params_count=non_trainable_params_count,
            non_trainable_params_size=non_trainable_params_size,
        )


class OutputStates(tp.NamedTuple):
    preds: tp.Any
    params: tp.Any
    states: tp.Any


@jax.tree_util.register_pytree_node_class
class States(tp.Mapping):
    def __init__(self, _data=None, **kwargs):
        self._data = dict(_data, **kwargs) if _data is not None else dict(**kwargs)

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __getattr__(self, key):
        if key not in self._data:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{key}'"
            )

        return self._data[key]

    def __setstate__(self, d):
        self._data = d

    def __getstate__(self):
        return self._data

    def update(self, **kwargs) -> "States":
        data = self._data.copy()
        data.update(kwargs)
        return States(data)

    def maybe_update(self, **kwargs) -> "States":

        kwargs = {
            key: value
            for key, value in kwargs.items()
            if key not in self._data or (self._data[key] is None and value is not None)
        }

        return self.update(**kwargs)

    def copy(self) -> "States":
        return jax.tree_map(lambda x: x, self)

    def tree_flatten(self):
        return (tuple(self._data.values()), tuple(self._data.keys()))

    @classmethod
    def tree_unflatten(cls, aux_data, children):
        return cls(zip(aux_data, children))


@dataclass
class Parameter:
    collection: str
    value: tp.Any


@dataclass
class Info:
    shape: tp.Tuple[int, ...]
    dtype: tp.Any


@dataclass
class ParameterSpec:
    collection: str
    info: tp.Any


class Initializer(Protocol):
    def __call__(self, shape: Shape, dtype: DType) -> np.ndarray:
        ...


class JitCallable(Protocol):
    def __call__(
        self, *args
    ) -> tp.Tuple[tp.Any, tp.Optional[Parameters], ParameterCollection]:
        ...


class InitJit(Protocol):
    def __call__(
        self,
        *,
        rng: tp.Optional[RNGSeq] = None,
        set_defaults: bool = False,
    ) -> JitCallable:
        ...


class ApplyJit(Protocol):
    def __call__(
        self,
        params: tp.Optional[Parameters],
        collections: ParameterCollection,
        *,
        training: bool = True,
        rng: tp.Optional[RNGSeq] = None,
        set_defaults: bool = False,
    ) -> JitCallable:
        ...


class MissingModule(Exception):
    pass


class MissingOptimizer(Exception):
    pass


class MissingMethod(Exception):
    pass


class DependencyUnavailable(Exception):
    pass


class ShapeMismatch(Exception):
    pass


class MissingParameter(Exception):
    pass


class NoContext(Exception):
    pass


class ModuleOrderError(Exception):
    pass


class SubmoduleNotRegistered(Exception):
    pass
