import sys
import data, models
import json
import mip
from datetime import timedelta
from typing import Dict, List, Tuple
from itertools import combinations

if 1 < len(sys.argv) <= 2:
    with open(sys.argv[1], 'r') as f:
        json_schedule = json.load(f)
else: raise ValueError('Provide the path to the json file')

schedule = data.load_data(json_schedule)

m = mip.Model()
works: Dict[Tuple[models.UserId, models.ShiftId], mip.Var] = {}
for sp in schedule.preferences:
    works[sp.user.id, sp.shift.id] = m.add_var(var_type=mip.BINARY)
    # Can the name be more descriptive? Will the output format support special characters?
# Apparently '<' is not implemented for LinExpr, only <=
# Constraints

## Technical, common sense constraints

# Do not exceed shift capacity
for shift in schedule.shifts:
    m += mip.xsum([v[1] for v in works.items() if v[0][1] == shift.id]) <= shift.capacity

# Do not assign a person to overlapping shifts
for i1, i2 in combinations(works.items(), r=2):
    u1, s1 = i1[0]
    w1 = i1[1]
    u2, s2 = i2[0]
    w2 = i2[1]
    if u1 == u2 and schedule.shift[s1] & schedule.shift[s2]:
        m += w1 + w2 <= 1 # Person can take either shift, but not both

# Maximum daily shifts = 1
for shifts_on_day in schedule.shifts_for_day.values():
    for user in schedule.users:
        m += mip.xsum([w for k, w in works.items() 
        if k[0] == user.id and schedule.shift[k[1]] in shifts_on_day
        ]) <= 1

## Health, safety, and legal constraints

# Let people sleep
for i1, i2 in combinations(works.items(), r=2):
    u1, s1 = i1[0]
    w1 = i1[1]
    S1 = schedule.shift[s1]
    u2, s2 = i2[0]
    w2 = i2[1]
    S2 = schedule.shift[s2]
    if u1 == u2 and S1 != S2 and S1.ends_late and S2.begin - S1.end <= timedelta(9):
        m += w1 + w2 <= 1 # Can't work both shifts, need sleep
      
# Min-max work hours
for user in schedule.users:
    m += (timedelta(hours=user.min_hours).total_seconds() <= 
        mip.xsum([w * schedule.shift[k[1]].length.total_seconds() for k, w in works.items()]) 
        <= timedelta(hours=user.max_hours).total_seconds())

# Objective function
# Unhappiness value = sum of preference scores for chosen shifts
# We want to minimize the maximum of the unhappiness values

# Calculate prefscores (unhappiness values) for each user
pscore: Dict[models.UserId, int] = {u.id:mip.LinExpr() for u in schedule.users}
for k, w in works.items():
    u, s = k
    pscore[u] = pscore[u] + schedule.preference[s, u] * w

def maxge(it):
    '''Max function that uses >= to compare instead of >'''
    m = it[0]
    for el in it[1:]:
        if el >= m: m = el
    return m

m.objective = mip.minimize(maxge(list(pscore.values())))

m.write('model.lp')
print('Model built, running solver')
status = m.optimize()

if status == mip.OptimizationStatus.OPTIMAL:
    print('optimal solution cost {} found'.format(m.objective_value))
elif status == mip.OptimizationStatus.FEASIBLE:
    print('sol.cost {} found, best possible: {}'.format(m.objective_value, m.objective_bound))
elif status == mip.OptimizationStatus.NO_SOLUTION_FOUND:
    print('no feasible solution found, lower bound is: {}'.format(m.objective_bound))
if status == mip.OptimizationStatus.OPTIMAL or status == mip.OptimizationStatus.FEASIBLE:
    print('solution found, written to file')
    sols = []
    for k, w in works.items():
        u, s = k
        if w.x is not None and w.x:
            sols.append({'user': u, 'shift': s})
    
    with open('solution.json', 'w') as f:
        json.dump(sols, f)

