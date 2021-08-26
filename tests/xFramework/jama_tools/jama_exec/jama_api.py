from py_jama_rest_client.client import JamaClient, AlreadyExistsException, UnauthorizedException, \
    ResourceNotFoundException, TooManyRequestsException, APIClientException, APIServerException, APIException
from py_jama_rest_client.client import Core
from halo import Halo
import json


class JamaClientHelper:
    """
    A class to reference the py_jama_rest_client api functions
    """
    def __init__(self, jama_url, username, password):
        """
        This class initializes the Jama Client and handles the API calls

        :jama_url: A string representing the url of the jama cloud to call the Jama API
        :username: A string representing the username of the person that is calling the Jama API
        :password: A string representing the password of the person that is calling the Jama API
        """
        self.jama_client = JamaClient(host_domain=jama_url, credentials=(username, password), oauth=True)
        self.jama_core = Core(host_name=jama_url, user_credentials=(username, password), oauth=True)
        self.spinner = Halo(text='Waiting for Jama API', spinner='dots')

    def get_project_id(self, project_name):
        """
        Return the project ID that matches with the project name that is passed as an argument

        Args:
            project_name: A string representing a JAMA project name

        Returns: An integer that indicates the project ID associated with the JAMA project
        """

        self.spinner.start("Retrieving project ID for " + project_name + " from Jama API")
        projects = self.jama_client.get_projects()
        self.spinner.stop()

        # Search through the projects available on Jama and find the matching name
        project_id = ''
        for project in projects:
            if isinstance(project, dict):
                if project_name == project['fields']['name'] and not project['isFolder']:
                    project_id = project['id']

        if project_id == '':
            raise Exception("No such JAMA project is named '" + project_name + "'")

        return project_id

    def get_all_responses(self, resource_path, params, allowed_results=10):
        """
        Will cycle through all items, even if they are paged
        Taken from https://community.jamasoftware.com/blogs/john-lastname/2017/09/29/managing-multiple-pages-of-results-in-the-jama-rest-api
        """
        max_results = "maxResults=" + str(allowed_results)  

        result_count = -1  
        start_index = 0  
        total_results = []
        while result_count != 0:  
            start_at = "startAt=" + str(start_index)
            url = resource_path + "?" + start_at + "&" + max_results
            response = self.jama_core.get(url, params=params)
            self.__handle_response_status(response)
            json_response = response.json()
            page_info = json_response["meta"]["pageInfo"]
            test_plans = json_response['data']
            total_results += test_plans
            start_index = page_info["startIndex"] + allowed_results  
            result_count = page_info["resultCount"]
        return total_results

    def get_test_plan_id(self, project_id, test_plan_name):
        self.spinner.start("Retrieving available Jama Test Plans")
        try:
            params = {"project": project_id}
            resource_path = "testplans"

            test_plans = self.get_all_responses(resource_path, params)
        except Exception as e:
            print("\n" + str(e))
            return -1
        self.spinner.stop()

        test_plan_id = ""
        for test_plan in test_plans:
            if test_plan['fields']['name'] == test_plan_name:
                test_plan_id = test_plan['id']

        if test_plan_id == '':
            raise Exception("No such JAMA test plan '" + test_plan_name + "' in the project that you entered")

        return test_plan_id

    def get_test_cycle_id(self, test_plan_id, test_cycle_name):
        self.spinner.start("Retrieving available Jama test cycles")
        try:
            resource_path = "testplans/" + str(test_plan_id) + "/testcycles"
            response = self.jama_core.get(resource_path)
            self.__handle_response_status(response)
            test_plans = response.json()['data']
        except Exception as e:
            print("\n" + str(e))
            return -1
        self.spinner.stop()

        test_cycle_id = ""
        for test_plan in test_plans:
            if test_plan['fields']['name'] == test_cycle_name:
                test_cycle_id = test_plan['id']

        if test_cycle_id == '':
            raise Exception("No such JAMA test cycle '" + test_cycle_name + "' in the test plan that you entered")

        return test_cycle_id

    def get_test_runs(self, test_cycle_id):
        self.spinner.start("Retrieving test cycle")
        try:
            response = self.jama_client.get_testruns(test_cycle_id)
        except Exception as e:
            print("\n" + str(e))
            return -1
        self.spinner.stop()
        return response

    def update_test_run(self, test_run, status, result_message, duration_in_seconds, user_jama_id, bulk_comment):
        test_run_id = test_run['id']
        test_run_steps = test_run['fields']['testRunSteps']
        for test_run_step in test_run_steps:
            test_run_step['status'] = status

        formatted_result_message = result_message.replace("\n", "</p>\n\n<p>")

        body = {
            "fields": {
                "testRunSteps": test_run_steps,
                "actualResults": formatted_result_message,
                "duration": int(duration_in_seconds * 1000),
                "assignedTo": user_jama_id,
                # "testRunComments$37": bulk_comment
            }
        }
        self.spinner.start("Pushing status '" + status + "' to test case: '" + test_run['fields']['name'] + "'")
        try:
            resource_path = "testruns/" + str(test_run_id)
            headers = {'content-type': 'application/json'}
            response = self.jama_core.put(resource_path, data=json.dumps(body), headers=headers)
            self.__handle_response_status(response)
        except Exception as e:
            print("\nUnable to push status '" + status + "' to test case: '" +
                  test_run['fields']['name'] + "' due to the following error: " + str(e))
            return -1
        self.spinner.stop()

        print("Pushed status " + status + " to test case: " + test_run['fields']['name'])

    def get_global_id_from_test_case_name_and_test_plan(self, project, project_id, test_case_name, test_plan_id):
        """
        Return the global id from the test case name and test plan id used

        Args:
            project: A string representing the project name of a JAMA project
            project_id: An integer representing the project ID of a JAMA project
            test_case_name: A string representing the test case name of a test case
            test_plan_id: An int representing the test plan ID of a test case

        Returns: An integer that represents the test case id of the test case
                 that has the same global id in the JAMA project that was passed in.
                 If there were no test case IDs, a -1 will be passed back
        """
        abstract_items = self.jama_client.get_abstract_items(project=[project_id], contains=[test_case_name])        

        if abstract_items:
            for test_case in abstract_items:
                if 'testPlan' in test_case['fields'].keys():
                    if test_case['fields']['testPlan'] == test_plan_id and test_case['fields']['name'].rstrip().lower() == test_case_name.rstrip().lower():
                        return int(test_case['globalId'].strip('GID-'))
        else:
            return -1

    def get_test_case_id_from_global_id(self, project, project_id, global_id):
        """
        Return the test case id based upon project ID and the global ID

        Args:
            project: A string representing the project name of a JAMA project
            project_id: An integer representing the project ID of a JAMA project
            global_id: An integer representing the global ID of a test case

        Returns: An integer that represents the test case id of the test case
                 that has the same global id in the JAMA project that was passed in.
                 If there were no test case IDs, a -1 will be passed back
        """

        self.spinner.start("Retrieving test case ID from Jama API")
        abstract_items = self.jama_client.get_abstract_items(project=[project_id], contains=[global_id])
        self.spinner.stop()

        # not particularly useful after refactor
        # if len(abstract_items) > 1:
        #     raise Exception("More than one test case with global id '" + global_id +
        #                     "' was found was found in project '" + project + "'")

        if abstract_items:
            for test_case in abstract_items:
                if test_case['globalId'] == global_id:
                    return test_case['id']
        else:
            return -1

    def get_current_user_id(self):
        self.spinner.start("Retrieving current user ID")
        try:
            resource_path = "users/current"
            response = self.jama_core.get(resource_path)
            self.__handle_response_status(response)
        except Exception as e:
            print("\n" + str(e))
            return -1
        self.spinner.stop()

        user_full_name = response.json()['data']['firstName'] + " " + response.json()['data']['lastName']
        if user_full_name:
            return response.json()['data']['id'], user_full_name
        else:
            raise Exception("\nUser has confirmed that the person who executed this was not " +
                            response.json()['data']['firstName'] + " " + response.json()['data']['lastName'])

    @staticmethod
    def __handle_response_status(response):
        """ Taken from https://github.com/jamasoftware-ps/py-jama-rest-client
                    Utility method for checking http status codes.
        If the response code is not in the 200 range, An exception will be thrown."""

        status = response.status_code

        if status in range(200, 300):
            return status

        if status in range(400, 500):
            """These are client errors. It is likely that something is wrong with the request."""

            response_message = 'No Response'

            try:
                response_json = json.loads(response.text)
                response_message = response_json.get('meta').get('message')

            except json.JSONDecodeError:
                pass

            if response_message is not None and "already exists" in response_message:
                raise AlreadyExistsException("Entity already exists.",
                                             status_code=status,
                                             reason=response_message)

            if status == 401:
                raise UnauthorizedException("Unauthorized: check credentials and permissions.  "
                                            "API response message {}".format(response_message),
                                            status_code=status,
                                            reason=response_message)

            if status == 404:
                raise ResourceNotFoundException("Resource not found. check host url.",
                                                status_code=status,
                                                reason=response_message)

            if status == 429:
                raise TooManyRequestsException("Too many requests.  API throttling limit reached, or system under "
                                               "maintenance.",
                                               status_code=status,
                                               reason=response_message)

            raise APIClientException("{} {} Client Error.  Bad Request.  "
                                     "API response message: {}".format(status, response.reason, response_message),
                                     status_code=status,
                                     reason=response_message)

        if status in range(500, 600):
            """These are server errors and network errors."""

            # Log The Error
            raise APIServerException("{} Server Error.".format(status),
                                     status_code=status,
                                     reason=response.reason)

        # Catch anything unexpected
        raise APIException("{} error".format(status),
                           status_code=status,
                           reason=response.reason)
