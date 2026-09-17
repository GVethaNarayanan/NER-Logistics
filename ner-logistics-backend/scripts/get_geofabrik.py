import requests
import re
html = requests.get('https://download.geofabrik.de/asia/india.html').text
for match in re.findall(r'href="(.*?\.pbf)"', html):
    print(match)
