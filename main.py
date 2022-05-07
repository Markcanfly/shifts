import sys
import data, models
import json
import mip
from datetime import timedelta, datetime
from typing import Dict, List, Tuple
from itertools import combinations

def name(id: str) -> str:
    '''Extract name from email'''
    return id.split('@')[0]

def shiftstr(s: models.Shift) -> str:
    '''
    LP-printable shift data
    Example: 25565@{03-11|15;30-19;30}
    '''
    s = schedule.shift[s.id]
    return f'{s.id}@{{{s.begin.month:02}-{s.begin.day:02}|{s.begin.hour:02};{s.begin.minute:02}-{s.end.hour:02};{s.end.minute:02}}}'

if len(sys.argv) == 5:
    fname = sys.argv[1]
    with open(fname, 'r') as f:
        json_schedule = json.load(f)
else: raise ValueError('Arguments: filepath solver worst_weight avg_weight')

schedule = data.load_data(json_schedule)
begin = datetime.now()
SOLVER = sys.argv[2]
if SOLVER not in (mip.GRB, mip.CBC): raise ValueError('Invalid solver name')
WORST_WEIGHT = int(sys.argv[3])
AVG_WEIGHT = int(sys.argv[4])
m = mip.Model(solver_name=SOLVER)
works: Dict[Tuple[models.UserId, models.ShiftId], mip.Var] = {}
for sp in schedule.preferences:
    works[sp.user.id, sp.shift.id] = m.add_var(f'{name(sp.user.id)}_works_{shiftstr(schedule.shift[sp.shift.id])}', var_type=mip.BINARY)
    # Can the name be more descriptive? Will the output format support special characters?
# Apparently '<' is not implemented for LinExpr, only <=
# Constraints

## Technical, common sense constraints

# Do not exceed shift capacity
for shift in schedule.shifts:
    m += mip.xsum([v[1] for v in works.items() if v[0][1] == shift.id]) <= shift.capacity, f'{shiftstr(schedule.shift[shift.id])}_capacity'

# Do not assign a person to overlapping shifts
for i1, i2 in combinations(works.items(), r=2):
    u1, s1 = i1[0]
    w1 = i1[1]
    u2, s2 = i2[0]
    w2 = i2[1]
    if u1 == u2 and schedule.shift[s1] & schedule.shift[s2]:
        m += w1 + w2 <= 1, f'{name(u1)}_cant_work_overlapping_shifts_{shiftstr(schedule.shift[s1])}_and_{shiftstr(schedule.shift[s2])}'

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
    if u1 == u2 and S1 != S2 and S1.ends_late and S2.begin - S1.end <= timedelta(hours=9) and S1.end <= S2.begin:
        m += w1 + w2 <= 1, f'{name(u1)}_cant_work_sleep_inconvenient_shifts_{shiftstr(schedule.shift[s1])}_and_{shiftstr(schedule.shift[s2])}'

# Min-max work hours
for user in schedule.users:
    work_time = mip.xsum([w * schedule.shift[k[1]].length.total_seconds() for k, w in works.items() if k[0] == user.id])
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

max_val = m.add_var('max_pscore')
for u in schedule.users:
    m += max_val >= pscore[u.id]

m.objective = mip.minimize(AVG_WEIGHT * mip.xsum(pscore.values()) + WORST_WEIGHT * max_val)
m.max_mip_gap = 0.00001 # Objective value max opt tolerance
m.write('model.lp')
print('Model built, running solver')
status = m.optimize(max_seconds=240)
end = datetime.now()
Walltime = str((end-begin).total_seconds())
if status == mip.OptimizationStatus.OPTIMAL:
    print('optimal solution cost {} found'.format(m.objective_value))
elif status == mip.OptimizationStatus.FEASIBLE:
    print('sol.cost {} found, best possible: {}'.format(m.objective_value, m.objective_bound))
elif status == mip.OptimizationStatus.NO_SOLUTION_FOUND:
    print('no feasible solution found, lower bound is: {}'.format(m.objective_bound))
    data.stats_to_xml(schedule, {}, None, Walltime, SOLVER, WORST_WEIGHT).write(fname.replace('.json', f'_{SOLVER}_{WORST_WEIGHT}_stat.xml'))
if status == mip.OptimizationStatus.OPTIMAL or status == mip.OptimizationStatus.FEASIBLE:
    print('solution found, written to file')
    sols = []
    for k, w in works.items():
        u, s = k
        if w.x is not None and w.x:
            sols.append({'user': u, 'shift': s})
    print(f'Worst prefscore: {max([v.x for v in pscore.values()])}')
    print(f'Sum prefscore: {sum([v.x for v in pscore.values()])}')
    print(f'Avg prefscore: {sum([v.x for v in pscore.values()]) / len(schedule.users)}')
    with open('solution.json', 'w') as f:
        json.dump(sols, f)
    data.stats_to_xml(schedule, pscore, sols, Walltime, SOLVER, WORST_WEIGHT, AVG_WEIGHT).write(fname.replace('.json', f'_{SOLVER}_{WORST_WEIGHT}_stat.xml'))
