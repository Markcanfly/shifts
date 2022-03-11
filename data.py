"""Handling of raw data from files"""
import json
from typing import List, Dict
from datetime import datetime
from models import Schedule, User, Shift, ShiftPreference
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
