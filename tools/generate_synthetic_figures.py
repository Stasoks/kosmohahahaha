#!/usr/bin/env python3
"""Generate documentation-only synthetic figures.

The values are deliberately unrelated to the competition input table.
"""
from pathlib import Path
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[1] / 'docs' / 'figures'
OUT.mkdir(parents=True, exist_ok=True)

periods = ['P1', 'P2', 'P3', 'P4']

# Figure 1: demand vs served and total available supply.
demand = [10, 13, 16, 19]
served = [10, 12, 15, 18]
supply = [11, 13, 17, 20]
plt.figure(figsize=(8, 4.8))
plt.plot(periods, demand, marker='o', label='Demand')
plt.plot(periods, served, marker='o', label='Served demand')
plt.plot(periods, supply, marker='o', label='Available supply')
plt.title('SYNTHETIC EXAMPLE — NOT A CASE SOLUTION\nSupply, demand and service')
plt.xlabel('Synthetic period')
plt.ylabel('Synthetic volume, t')
plt.legend()
plt.tight_layout()
plt.savefig(OUT / 'synthetic_supply_vs_demand.svg', dpi=160)
plt.close()

# Figure 2: inventory trace and reserve threshold.
inventory = [5, 7, 4, 8]
reserve = [4, 4.5, 5, 5.5]
plt.figure(figsize=(8, 4.8))
plt.plot(periods, inventory, marker='o', label='Closing inventory')
plt.plot(periods, reserve, marker='o', label='Reserve threshold')
plt.title('SYNTHETIC EXAMPLE — NOT A CASE SOLUTION\nInventory versus reserve threshold')
plt.xlabel('Synthetic period')
plt.ylabel('Synthetic volume, t')
plt.legend()
plt.tight_layout()
plt.savefig(OUT / 'synthetic_inventory_and_reserve.svg', dpi=160)
plt.close()

# Figure 3: cost decomposition.
categories = ['Procurement', 'Reservation', 'Holding', 'OPEX', 'CAPEX']
values = [42, 8, 3, 6, 15]
plt.figure(figsize=(8, 4.8))
plt.bar(categories, values)
plt.title('SYNTHETIC EXAMPLE — NOT A CASE SOLUTION\nIllustrative cost decomposition')
plt.ylabel('Synthetic cost units')
plt.xticks(rotation=20, ha='right')
plt.tight_layout()
plt.savefig(OUT / 'synthetic_cost_breakdown.svg', dpi=160)
plt.close()
