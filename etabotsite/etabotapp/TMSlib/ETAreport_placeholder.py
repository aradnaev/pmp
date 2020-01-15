"""Reports."""

import pandas as pd
import numpy as np


def generate_status_report(ETApredict_obj, **kwargs):
    """Generate total report.

    Arguments:
    ETApredict_obj - ETApredict class object, must have task_list.

    Returns: 
    json with hierarchical information.

    """
    report = {
        'projects_on_track': 1,
        'projects_total': 1,
        'deadlines_on_track': 3,
        'deadlines_total': 5,
        'projects':{
            'Cheburashka':{
                'overdue':[
                    {
                        'task': 'build friends house',
                        'due_date': 'Oct 2019',
                        'ETA': 'Jan 2020',
                        'link': 'https://xkcd.com?id=123'
                    },
                    {
                        'task': 'meet with Shapoklyak',
                        'due_date': 'Sep 2019',
                        'ETA': 'Feb 2020',
                        'link': 'https://xkcd.com?id=123'
                    }
                    ],
                'on_track': [
                    {
                        'task': 'clean river',
                        'due_date': 'Feb 2020',
                        'ETA': 'Jan 2020',
                        'link': 'https://xkcd.com?id=123'
                    },
                    {
                        'task': 'plan Japan trip',
                        'due_date': 'March 2020',
                        'ETA': 'Feb 2020',
                        'link': 'https://xkcd.com?id=123'
                    }
                    ]
                },
            'Buckwheat': {
                'overdue':[
                    {
                        'task': 'roast buckwheat',
                        'due_date': 'Oct 2019',
                        'ETA': 'Jan 2020',
                        'link': 'https://xkcd.com?id=123'
                    }
                    ],
                'on_track': [
                    {
                        'task': 'buy buckwheat',
                        'due_date': 'March 2020',
                        'ETA': 'Feb 2020',
                        'link': 'https://xkcd.com?id=123'
                    }
                    ]
                }                
            }

        }
    return report
