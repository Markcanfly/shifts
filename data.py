"""Handling of raw data from files"""
from typing import List, Dict
from datetime import datetime
from models import Schedule, User, Shift, ShiftPreference, UserId
import xml.etree.ElementTree as ET
import pytz

def filter_unique_ordered(l):
    """Filter a list so that the items are unique.
    When an item appears more than once, the first occurrence will be retained.
    """
    occured = set()
    filtered = []
    for elem in l:
        if elem not in occured:
            occured.add(elem)
            filtered.append(elem)
    return filtered

timestamp = int
def datetime_string(ts: timestamp) -> str:
    return datetime.fromtimestamp(int(ts)).isoformat()

def get_shifts(rshifts: List[Dict], timezone: str) -> List[Shift]:
    """Creates the necessary shift dict format
    Arguments:
        rshifts: rshifts
        timezone: timezone name
    Returns:
        list of Shifts
    """
    shifts = list()
    for shift in rshifts:
        begin = datetime.fromtimestamp(int(float(shift['begin']))).astimezone(pytz.timezone(timezone))
        end = datetime.fromtimestamp(int(float(shift['end']))).astimezone(pytz.timezone(timezone))
        shifts.append(
            Shift(
                id=int(shift['id']),
                begin=begin,
                end=end,
                capacity=shift['capacity'],
                position=shift['position']
            )
        )
    return shifts

def get_users(rusers: List[Dict]) -> List[User]:
    """Get the schedule requirements for this person
    Arguments:
        users: [
            {
                email
                hours_adjusted
                hours_max
                preferences
                positions
            }
        ]
        min_ratio: float, ratio of min hours to max hours
    Returns:
        list of users
    """ # WARNING highly custom code for Wolt Hungary
    users = list()
    for user in rusers:
        min_hours = user['hours_adjusted']**0.89 if user['hours_max'] >= 35 else 0.6 * user['hours_adjusted']
        users.append(
            User(
                id=user['email'],
                min_hours=min_hours,
                max_hours=user['hours_adjusted'],
                only_long=(user['hours_max'] >= 35), # Fulltimer or not
                min_long=1,
                positions=user['positions']
            )
        )
    return users

def get_preferences(users: List[User], shifts: List[Shift], rusers: List[dict]) -> List[ShiftPreference]:
    # Index by id
    user = {u.id:u for u in users}
    shift = {s.id:s for s in shifts}
    preferences = []
    for ruser in rusers:
        for rshiftid, priority in ruser['preferences'].items():
            preferences.append(ShiftPreference(
                user=user[ruser['email']],
                shift=shift[int(rshiftid)],
                priority=priority
            ))
    return preferences

def load_data(data: dict) -> Schedule:
    """
    Args:
        data: {
            'shifts': [
                {
                    'id': int
                    'begin': timestamp
                    'end': timestamp
                    'capacity': int
                    'position': wiw_id
                }
            ]
            'timezone': tzname
            'users' [
                {
                    'email': str
                    'hours_adjusted': float
                
                    'hours_max': float
                    'wiw_id': wiw_id
                    'preferences': {
                        shiftid: priority
                    }
                }
            ]
        }
    Returns:
        Schedule with the associated data"""
    rshifts = data['shifts']
    rtimezone = data['timezone']
    rusers = data['users']
    shifts = get_shifts(rshifts, rtimezone)
    users = get_users(rusers)
    preferences = get_preferences(users, shifts, rusers)
    return Schedule(users,shifts,preferences)

def stats_to_xml(schedule: Schedule, pscore: Dict, solutions: List[Dict], wall: int, solver_name: str, worst_weight: int, avg_weight: int) -> ET.ElementTree:
    root = ET.Element('Schedule')
    ET.SubElement(root, 'Name').text = f'{min([s.begin for s in schedule.shifts])}-{max([s.end for s in schedule.shifts])}'
    solstats = ET.SubElement(root, 'Solution')
    pscore_values = [v.x for v in pscore.values()]
    ET.SubElement(solstats, 'Solver').text = solver_name
    if solutions is None:
        if wall >= 230: # idk
            ET.SubElement(solstats, 'Status').text = 'Timeout'
        else:
            ET.SubElement(solstats, 'Status').text = 'Unsolvable'
    else:
        ET.SubElement(solstats, 'Status').text = 'Solved'
    ET.SubElement(solstats, 'WorstScoreObjWeight').text = str(worst_weight)
    ET.SubElement(solstats, 'AvgScoreObjWeight').text = str(avg_weight)
    ET.SubElement(solstats, 'WorstPrefScore').text = str(int(max(pscore_values)))
    ET.SubElement(solstats, 'AvgPrefScore').text = str(sum(pscore_values) / len(schedule.users))
    ET.SubElement(solstats, 'SumPrefScore').text = str(int(sum(pscore_values)))
    ET.SubElement(solstats, 'Walltime').text = str(wall)
    schedstats = ET.SubElement(root, 'Info')
    ET.SubElement(schedstats, 'NShifts').text = str(len(schedule.shifts))
    ET.SubElement(schedstats, 'NCapacities').text = str(sum([s.capacity for s in schedule.shifts]))
    ET.SubElement(schedstats, 'NUsers').text = str(len(schedule.users))
    shifts = ET.SubElement(root, 'Shifts')
    for shift in schedule.shifts:
        shiftel = ET.SubElement(shifts, 'Shift')
        ET.SubElement(shiftel, 'ID').text = str(shift.id)
        ET.SubElement(shiftel, 'Begin').text = str(int(shift.begin.timestamp()))
        ET.SubElement(shiftel, 'End').text = str(int(shift.end.timestamp()))
        ET.SubElement(shiftel, 'Duration').text = str(int(shift.length.total_seconds()))
        solved_user = ET.SubElement(shiftel, 'User')
        try: solved_user.text = str([d['user'] for d in solutions if d['shift'] == shift.id][0])
        except IndexError: solved_user.text = None
        prefs = ET.SubElement(shiftel, 'Preferences')
        for pref in schedule.preferences:
            if pref.shift != shift:
                continue
            prefel = ET.SubElement(prefs, 'Preference')
            ET.SubElement(prefel, 'User').text = str(pref.user.id)
            ET.SubElement(prefel, 'Score').text = str(pref.priority)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t", level=0)
    return tree
