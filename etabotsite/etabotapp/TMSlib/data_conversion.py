"""Collection of data conversion tools."""
import logging
import numpy as np

def np_json_value(x):
    """Ensures values are json compabible."""
    if np.isnan(x):
        return None
    else:
        return str(x)

def get_velocity_json(velocities, project_name):
    """Creates velocity json for UI from velocities python object
    for a project named project_name"""
    velocity = velocities.get(project_name)
    velocity_json = {
        'mean': None,
        'upper_estimate': None,
        'lower_estimate': None
    }
    if velocity is not None:
        velocity_json['mean'] = np_json_value(velocity.value)
        velocity_json['upper_estimate'] = np_json_value(velocity.higher_estimate())
        velocity_json['lower_estimate'] = np_json_value(velocity.lower_estimate())
    else:
        logging.debug('velocity is None for project {}'.format(
            project_name))
    return velocity_json
