from dataclasses import dataclass , field 
from typing import Optinal , List , Dict 
import numpy 
@dataclass
class MCLP:
    p : np.ndarray
    a : np.ndarray
    c : np.ndarray
    P_max : Optinal[int]