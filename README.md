# Conformal Deposition Dent Model

Interactive Python tool for plotting how conformal deposition changes dent depth.

## What It Plots

- `x`: conformal deposition amount
- `y`: remaining dent depth after deposition
- `W`: dent width controlled by the user
- `D`: initial dent depth controlled by the user
- `z`: maximum tangent angle of the deposited top surface, where a flat surface is `0 deg`

The graph plots `y(x)` and `z(x)` together. The right-side profile plot shows the initial dent and the deposited shape at the selected deposition amount.

## Run

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Or double-click:

```text
run_app.bat
```

## Model

The app treats the 2D dent boundary as the original exposed surface and expands it by the deposition distance `x`. The deposited flat field is at height `x`. The remaining dent depth is:

```text
y = deposited flat top height - lowest deposited surface inside the dent opening
```

The angle `z` is computed from the maximum absolute local slope of the deposited top boundary:

```text
z = atan(max(abs(dy/dx)))
```
