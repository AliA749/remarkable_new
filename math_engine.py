"""Takes the latex gemini transcribed and turns it into either: a graph or a solved result"""

import os
import matplotlib
matplotlib.use("Agg")#no display needed
import matplotlib.pyplot as plt
import numpy as np
import sympy
from sympy.parsing.latex import parse_latex

from config import RESULTS_DIR

class MathResult:
    def __init__(self, kind:str, text: str, image_path:str |None=None):
        self.kind=kind #graph, solved,simplifed or error
        self.text=text #human-readable summary
        self.image_path = image_path

    def __repr__(self):
        return f"MathResult(kind={self.kind!r}, text={self.text!r}, image_path={self.image_path!r})"

def _parse(latex_str:str):
    """parse_latex chokes on some OCR quirks (e.g. stray spaces); do minimal cleanup."""
    cleaned=latex_str.strip()
    return parse_latex(cleaned)

def _plot_function(expr, var, out_path:str, x_range=(-10,10)):
    f= sympy.lambdify(var, expr, modules=["numpy"])
    xs=np.linspace(x_range[0],x_range[1],400)
    with np.errstate(all='ignore'):
        ys=f(xs)
    ys=np.array(ys,dtype=float)

    fig,ax=plt.subplots(figsize=(6,4))
    ax.plot(xs,ys)
    ax.axhline(0,color="gray", linewidth=0.5)
    ax.axvline(0,color="gray",linewidth=0.5)
    ax.set_title(f"${sympy.latex(expr)}$")
    fig.tight_layout()
    fig.savefig(out_path,dpi=150)
    plt.close(fig)

def decide_and_render(latex_str: str, out_name:str ="math_result.png")->MathResult:
    out_path=os.path.join(RESULTS_DIR, out_name)

    try:
        parsed=_parse(latex_str)
    except Exception as e:
        return MathResult("error",f"Couldn't parse LaTeX {e}")
    free_vars=sorted(parsed.free_symbols,key=str)

    #case 1: an equation (has Eq mode), e.g. "2x + 3=7" or "y=x^2"
    if isinstance(parsed, sympy.Eq):
        lhs,rhs=parsed.lhs, parsed.rhs
        # "y = <expr in x>" pattern -> treat as a function to plot
        if lhs.is_symbol and lhs not in rhs.free_symbols and len(free_vars)==2:
            x_var =rhs.free_symbols.pop()
            _plot_function(rhs, x_var,out_path)
            return MathResult("graph", f"plotted {lhs}={rhs}",out_path)
        # Otherwise, solve algebraically for whichever variable(s) it has
        if free_vars:
            solutions=sympy.solve(parsed, free_vars[0])
            return MathResult(
                'Solved',
                f"{latex_str} -> {free_vars[0]}={solutions}",
            )
        return MathResult("Solved",f"{latex_str}->{parsed}")
    #Case 2: plain expression with exactly one free variable -> plot it as f(x)
    if len(free_vars)==1:
        _plot_function(parsed, free_vars[0], out_path)
        return MathResult("graph", f"Plotted f({free_vars[0]}) = {parsed}", out_path)
    # Case 3: no free variables -> just simplify/evaluate
    simplified = sympy.simplify(parsed)
    return MathResult("simplified", f"{latex_str} = {simplified}")

if __name__=="__main__":
    import sys
    if len(sys.argv) !=2:
        print("Usage: python math_engine.py '<latex string>'")
        sys.exit(1)
    result = decide_and_render(sys.argv[1])
    print(result)
    
