from datetime import datetime, date, timedelta

def serialize_data(data):

    for row in data:

        for key, value in row.items():

            if isinstance(value, timedelta):
                row[key] = str(value)

            elif isinstance(value, (datetime, date)):
                row[key] = value.strftime("%Y-%m-%d %H:%M:%S")

    return data