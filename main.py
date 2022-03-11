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
    works[sp.user.id, sp.shift.id] = m.add_var(f'{sp.user.id} works {sp.shift.id}', var_type=mip.BINARY)
    # Can the name be more descriptive? Will the output format support special characters?
# Apparently '<' is not implemented for LinExpr, only <=
# Constraints

## Technical, common sense constraints

# Do not exceed shift capacity
for shift in schedule.shifts:
    m += mip.xsum([v[1] for v in works.items() if v[0][1] == shift.id]) <= shift.capacity

# Do not assign a person to overlapping shifts
for k1, w1 in works.items():
    u1, s1 = k1
    for k2, w2 in works.items():
        u2, s2 = k2
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
for k1, w1 in works.items():
    u1, s1 = k1
    S1 = schedule.shift[s1]
    for k2, w2 in works.items():
        u2, s2 = k2
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
    pscore[u] += schedule.preference[s, u] * w
'''Exception has occurred: DeprecationWarning
Inplace operations are deprecated
  File "/Users/markvarga/Documents/Documents – Mark’s MacBook Pro/workspace/python/solver/shifts/main.py", line 71, in <module>
    pscore[u] += schedule.preference[s, u] * w
    '''

m.objective = mip.minimize(
    max(list(pscore.values()))
    ) # does this work

m.write('model.lp')
