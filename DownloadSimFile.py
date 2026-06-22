"""
This script downloads a file from a specified URL and saves it locally.
The file being downloaded is "DispensingSystem.vcmx" from a GitHub repository. 
Idea is to get the URL from the Simualation Submodel for each asset on the AAS.
This should be used to download the latest version of the simulation layout 
for the dispensing system, which can then be used in the visual component of the simulation.

The AAS integration has not been implmented yet, so the URL is hardcoded for now. In the future, this script can be modified to fetch the URL from the AAS submodel instead of hardcoding it.
"""

import requests

url = "https://raw.githubusercontent.com/AAU-RoboticsAutomationGroup/AAU-Visual-Component-w-AAS-UNS/main/Layouts/DispensingSystem.vcmx"
output_file = "DispensingSystem.vcmx"

response = requests.get(url)

if response.status_code == 200:
    with open(output_file, "wb") as f:
        f.write(response.content)
    print(f"Downloaded successfully to {output_file}")
else:
    print(f"Failed to download file. Status code: {response.status_code}")