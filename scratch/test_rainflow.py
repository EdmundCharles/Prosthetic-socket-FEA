import numpy as np
import rainflow

# Simulate a typical gait load history: 0 -> peak1 -> valley -> peak2 -> 0
t = np.linspace(0, 1, 100)
# A typical double-peak vertical force curve
force = 1.1 * np.sin(np.pi * t) + 0.2 * np.sin(3 * np.pi * t)
# Ensure it starts and ends at 0
force = np.clip(force, 0, None)

print("Force series shape:", force.shape)
print("Force min/max:", np.min(force), np.max(force))

# Extract cycles
cycles = list(rainflow.extract_cycles(force))
print("Extracted cycles:")
for c in cycles:
    print(c)
