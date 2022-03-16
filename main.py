import sys
import data, models
import json
import mip
import re
from datetime import timedelta
from typing import Dict, List, Tuple
from itertools import combinations

def name(id: str) -> str:
    '''Extract name from email'''
    return id.split('@')[0]

def aname(num) -> str:
    '''Alpha name from number'''
    if not isinstance(num, int):
        raise ValueError(f'{num} should be int to call this')
    v = 'abcdefghij'
    return ''.join([v[int(c)] for c in list(str(num))])

if 1 < len(sys.argv) <= 2:
    with open(sys.argv[1], 'r') as f:
        json_schedule = json.load(f)
else: raise ValueError('Provide the path to the json file')

schedule = data.load_data(json_schedule)

m = mip.Model()
works: Dict[Tuple[models.UserId, models.ShiftId], mip.Var] = {}
for sp in schedule.preferences:
    works[sp.user.id, sp.shift.id] = m.add_var(f'{name(sp.user.id)}_works_{aname(sp.shift.id)}', var_type=mip.BINARY)
    # Can the name be more descriptive? Will the output format support special characters?
# Apparently '<' is not implemented for LinExpr, only <=
# Constraints

## Technical, common sense constraints

# Do not exceed shift capacity
for shift in schedule.shifts:
    m += mip.xsum([v[1] for v in works.items() if v[0][1] == shift.id]) <= shift.capacity, f'{aname(shift.id)}_capacity'

# Do not assign a person to overlapping shifts
for i1, i2 in combinations(works.items(), r=2):
    u1, s1 = i1[0]
    w1 = i1[1]
    u2, s2 = i2[0]
    w2 = i2[1]
    if u1 == u2 and schedule.shift[s1] & schedule.shift[s2]:
        m += w1 + w2 <= 1, f'{name(u1)}_cant_work_overlapping_shifts_{aname(s1)}_and_{aname(s2)}'

# Maximum daily shifts = 1
for day, shifts_on_day in schedule.shifts_for_day.items():
    for user in schedule.users:
        m += mip.xsum([w for k, w in works.items() 
        if k[0] == user.id and schedule.shift[k[1]] in shifts_on_day
        ]) <= 1, f'{name(user.id)}_max_shift_for_day_{day}'

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
        m += w1 + w2 <= 1, f'{name(u1)}_cant_work_sleep_inconvenient_shifts_{aname(s1)}_and_{aname(s2)}'
      
# Min-max work hours
for user in schedule.users:
    work_time = mip.xsum([w * schedule.shift[k[1]].length.total_seconds() for k, w in works.items()])
    m += timedelta(hours=user.min_hours).total_seconds() <= work_time, f'{name(user.id)}_works_min_{int(timedelta(hours=user.min_hours).total_seconds())}_seconds'
    m += work_time <= timedelta(hours=user.max_hours).total_seconds(), f'{name(user.id)}_works_max_{int(timedelta(hours=user.max_hours).total_seconds())}_seconds'

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

