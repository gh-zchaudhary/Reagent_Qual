#!/usr/bin/env python
# content of jama_exec.py

import argparse
import sys
import glob
import html

from jama_api import JamaClientHelper
import io
import os
import fileinput
import json
import traceback
from junitparser import JUnitXml
from result_test import TestResult


def initialize_jama_client(jama_username, jama_password, config):
    """
    Return an initialized JamaClientHelper

    Args:
        jama_username: Username for the jama client in the constants
        jama_password: Password for the jama client in the constants

    Returns: A string containing the test case section
    """
    return JamaClientHelper(config['jama_url'], jama_username, jama_password)


def parse_args(args):
    """
    Return an ArgumentParser object containing the arguments passed in

    Args:
        args: A list of arguments to be parsed

    Returns: An ArgumentParser object containing the arguments passed in
    """
    parser = argparse.ArgumentParser(description='update Jama test cases based upon a provided pytest file path')
    parser.add_argument("--username", help="password (client ID) for current jama api user")
    parser.add_argument("--password", help="password (client secret) for current jama api user")
    parser.add_argument("--config_file", help="Path to config.json (default is same directory as executable)", required=False, default='config.json')
    parser.add_argument("--config_path", help="Path to config.json (default is same directory as executable)", required=False, default=os.path.dirname(__file__))    
    parser.add_argument("--compare", help="Compare tests in xml and jama test plan and show overlap and outliers", required=False, action='store_true', default=False)
    return parser.parse_args(args)


def check_report_id_in_test_plan(report_id, jama_test_plan, compare):
    """
    Check that the Report ID is in the Jama Test Plan name

    Args:
        report_id: A string representing a Report ID
        jama_test_plan: A string representing a Jama Test Plan name
    """
    if report_id not in jama_test_plan and not compare:
        raise Exception("\nReport id '" + report_id + "' is not listed in the Jama test plan '" +
                        jama_test_plan + "', please add the report id to the Jama test plan and try again")


def check_version_in_test_cycle(test_version, jama_test_cycle):
    """
    Check that the version of the software that was tested is in the Jama Test Cycle name

    Args:
        test_version: A string representing the test version of the software that was tested
        jama_test_cycle: A string representing a Jama Test Cycle name
    """
    if test_version not in jama_test_cycle:
        raise Exception("\nTest version '" + test_version + "' is not listed in the Jama test cycle '" +
                        jama_test_cycle + "', please add the test version and release candidate to " +
                        "the Jama test cycle and try again")


def read_results_from_suites(xml_suite, test_results_list, config):
    """
    Read the output xml file (formatted to read from a suite) and return a list of Test Result objects

    Args:
        xml_suite: An xml file output formatted as a single xml suite
        test_results_list: A list of test results that test results are getting added to

    Returns: A list of Test Result objects
    """
    for case in xml_suite:
        case_name = html.unescape(case.name)
        if case.result and hasattr(case.result, '_tag'):
            if case.result._tag != "skipped":
                new_result = TestResult(case_name, case.time, "FAILED")
                new_result.set_failed(case.result._tag, case.result.message,
                                      config['jama_test_plan'], config['test_version_and_release_candidate'])
                test_results_list.append(new_result)
        else:
            new_result = TestResult(case_name, case.time, "PASSED")
            new_result.set_passed(config['jama_test_plan'], config['test_version_and_release_candidate'])
            print(f'THIS IS THE CASE NAME {case_name}')
            test_results_list.append(new_result)
    return test_results_list


def read_output_xml_file(xml_file, config):
    """
    Read the output xml file and return a list of Test Result objects

    Args:
        xml_file: A string that contains the path to the xml output file that will be read

    Returns: A list of Test Result objects
    """
    xml = JUnitXml.fromfile(xml_file)
    test_results_read = []
    # Typically reading from a pytest output xml when the first tag is "testsuites".
    # We shouldn't be using this ._tag like below as it's protected by the class but there's currently no cleaner way \
    # to get this other than turning the element into a string and looking for expected keywords
    if xml._tag == "testsuites":
        print("---------------------Reading from " + xml_file + "---------------------")
        for suite in xml:
            test_results_read = read_results_from_suites(suite, test_results_read, config)
        return test_results_read
    # typically reading from a robot output xml with this
    else:
        print("---------------------Reading from " + xml_file + "---------------------")
        return read_results_from_suites(xml, test_results_read, config)


def get_test_case_jama_ids(jama_client, project, test_results, test_case_type, test_plan_name, compare=False):
    """
    Check that the version of the software that was tested is in the Jama Test Cycle name

    Args:
        jama_client: An initialized jama client object made from the JamaClientHelper
        project: A string representing the Jama project that the test runs live in
        test_results: A list of test result objects
        test_case_type: A string representing the framework that was used to output the xml results (ex: pytest)
        test_plan_name: A string reprenting the Jama test plan name
        compare: A boolean for if to compare or to try to upload test executions

    Returns: An array of TestCase objects representing all test case information that was passed in
    """
    valid_test_case_types = ["pytest", "robot"]
    if test_case_type not in valid_test_case_types:
        raise Exception("Jama Exec does not currently support '" + test_case_type +
                        "' types of test case updates currently. Please enter one of the valid test case types:" +
                        str(valid_test_case_types))

    project_id = jama_client.get_project_id(project)
    test_plan_id = jama_client.get_test_plan_id(project_id, test_plan_name)

    # Go through the test results and retrieve the global ID (might be needed for later) and test case ID
    # then return the test results with the Jama IDs set
    
    results_not_in_jama = []
    if test_case_type == "pytest":
    # add in additional loop so we can know all of the test cases that are not in Jama
        for test_result in test_results:
            global_id = None
            if not test_result.name.startswith("test_gid_") and not compare:
                results_not_in_jama.append(test_result.name)
            else:
                global_id = jama_client.get_global_id_from_test_case_name_and_test_plan(project, project_id, test_result.name, test_plan_id)
        if results_not_in_jama:
            raise Exception("Error in test case names. Expecting 'test_gid_' "
                            "in the following pytest test case name:", results_not_in_jama)

        for test_result in test_results:
            global_id = 'GID-' + test_result.name.strip("test_gid_").split("_")[0]
            test_result.set_jama_global_id(global_id)
            test_case_id = jama_client.get_test_case_id_from_global_id(project, project_id, global_id)
            test_result.set_jama_test_case_id(test_case_id)
        return test_results

    elif test_case_type == "robot":
        for test_result in test_results:
            if not test_result.name.startswith("TC-GID-") and not compare:
                results_not_in_jama.append(test_result.name)
        
        if results_not_in_jama:
            raise Exception("Error in test case names. Expecting 'TC-GID-' "
                            "in the following robot test case name:", results_not_in_jama)
        
        for test_result in test_results:
            global_id = None
            if test_result.name.startswith("TC-GID-") or test_result.name.startswith("test_gid_"):
                global_id = test_result.name.strip("TC-").split(":")[0]
            else:
                global_id = jama_client.get_global_id_from_test_case_name_and_test_plan(project, project_id, test_result.name, test_plan_id)
            test_result.set_jama_global_id(global_id)
            test_case_id = jama_client.get_test_case_id_from_global_id(project, project_id, global_id)
            test_result.set_jama_test_case_id(test_case_id)
        return test_results


def notify_user_of_deltas(in_executed_but_not_in_jama_delta, in_jama_but_not_in_executed_delta, in_jama_and_in_executed, executed_name_off, in_jama_name_off, compare, output_dir):
    """
    Prints the delta in command line

    Args:
        in_executed_but_not_in_jama_delta: A list containing test case names that were executed but not in jama
        in_jama_but_not_in_executed_delta: A list containing test case names that are in jama but were not executed
        in_jama_and_in_executed: A list containing test case names that are in jama and were executed
        executed_name_off: A list of test cases categorized as being flagged that may need an intervention to be updated
        in_jama_name_off: A list of test cases categorized as being flagged that may need an intervention to be updated
        compare: A bool where test cases were not executed but were just compared
        output_dir: A string representing a path to right an output file if compare is set to true
    """
    executed_not_in_jama_str = f"The following {len(in_executed_but_not_in_jama_delta)} test cases were in the execution but NOT in the Jama Test Plan:" if compare else "The following test cases were executed but NOT in the Jama Test Plan:" 
    executed_in_jama_str = f"The following {len(in_jama_but_not_in_executed_delta)} test cases were in the Jama Test Plan but not executed:" if compare else "The following test cases were in the Jama Test Plan but were NOT executed:"
    
    notification_str = ""
    if in_executed_but_not_in_jama_delta or in_jama_but_not_in_executed_delta:
        notification_str += "\n--------------------USER WARNINGS--------------------"
        if in_executed_but_not_in_jama_delta:
            notification_str += "\n" + executed_not_in_jama_str
            for test_case in in_executed_but_not_in_jama_delta:
                notification_str += "\n" + "     " + test_case

        # Spacer
        if in_executed_but_not_in_jama_delta and in_jama_but_not_in_executed_delta:
            notification_str += "\n"

        if in_jama_but_not_in_executed_delta:
            notification_str += "\n" + executed_in_jama_str
            for test_case in in_jama_but_not_in_executed_delta:
                notification_str += "\n" + "     " + test_case

        if executed_name_off and compare:
            notification_str += "\n\n" + f"The following {len(executed_name_off)} test cases have representatives that are very close to equal in execution:"
            for test_case in executed_name_off:
                notification_str += "\n" + "     " + test_case

        if in_jama_name_off and compare:
            notification_str += "\n\n" + f"The following {len(in_jama_name_off)} test cases have representatives that are very close to equal in Jama test plan:"
            for test_case in in_jama_name_off:
                notification_str += "\n" + "     " + test_case

        notification_str += "\n" + "--------------------USER WARNINGS--------------------"
        
        if in_jama_and_in_executed and compare:
            notification_str += "\n" + f"-----------------IN JAMA AND EXECUTED---------------"
            notification_str += "\n" + f"The following {len(in_jama_and_in_executed)} test cases were in the execution and in the Jama Test Plan:"
            for test_case in in_jama_and_in_executed:
                notification_str += "\n" + "     " + test_case
    # print(notification_str)

    if compare and output_dir:
        with open(os.path.join(output_dir, "jama_exec.log"), "w") as w:
            w.write(notification_str)


def read_output_and_format(jama_client, project, path_to_output, framework_type, test_plan_name, config, compare=False):
    """
    Read an output xml file and return a list of test result objects containing the result information

    Args:
        jama_client: An initialized jama client object made from the JamaClientHelper
        project: A string representing the Jama project that the test runs live in
        path_to_output: The path to the output xml file
        framework_type: A string representing the framework that was used to output the xml results (ex: pytest)
        config: Dictionary of variables
        test_plan_name: A str for the Jama test plan

    Returns: A list of test result objects containing the result information
    """
    # Read an output xml file and get the test results object list
    test_results = read_output_xml_file(path_to_output, config)
    # Get test case Jama IDs associated with test cases in the test results
    test_results_with_ids = get_test_case_jama_ids(jama_client, project, test_results, framework_type, test_plan_name, compare)

    return test_results_with_ids


def find_similar_test_cases_executed_in_plan(executed_but_not_in_jama_test_plan, jama_test_plan_but_not_in_executed, compare):
    """
    Compare
    executed_but_not_in_jama_test_plan: list of test cases in robot or pytest, but not found in Jama test plan
    jama_test_plan_but_not_in_executed: list of test cases in Jama test plan, but not found in robot or pytest
    compare: bool
    """
    executed_name_off, in_jama_name_off, executed_but_not_in_jama_test_plan_from_dict, jama_test_plan_but_not_in_executed_from_dict = [], [], [], []
    
    if compare:
        # convert to a dict with the prefix as key and suffix as value
        ex_not_in_jama_dict = dict()
        for test_case in executed_but_not_in_jama_test_plan:
            test_case_split = test_case.split(':', 1) if ':' in test_case else [test_case, test_case]
            ex_not_in_jama_dict[test_case_split[0]] = test_case_split[1]

        # convert to a dict and compare test case to ex_not_in_jama_dict
        in_jama_not_ex_dict = dict()
        for test_case in jama_test_plan_but_not_in_executed:
            test_case_split = test_case.split(':', 1) if ':' in test_case else [test_case, test_case]
            in_jama_not_ex_dict[test_case_split[0]] = test_case_split[1]
            if test_case_split[0] in ex_not_in_jama_dict.keys() and test_case not in in_jama_name_off:
                in_jama_name_off.append(test_case)
            elif test_case_split[1] in ex_not_in_jama_dict.values() and test_case not in in_jama_name_off:
                in_jama_name_off.append(test_case)
            else:
                #test_case_unsplit = test_case_split[0] + ':' + test_case_split[1] if test_case_split[0] != test_case_split[1] else test_case_split[0]
                if test_case not in executed_but_not_in_jama_test_plan_from_dict:
                    executed_but_not_in_jama_test_plan_from_dict.append(test_case)
    
        # ex_not_in_jama_dict items to in_jama_not_ex_dict
        for prefix, suffix in ex_not_in_jama_dict.items():
            test_case_unsplit = prefix + ':' + suffix if prefix != suffix else prefix
            if prefix in in_jama_not_ex_dict.keys() and test_case_unsplit not in executed_name_off:
                executed_name_off.append(test_case_unsplit)
            elif suffix in in_jama_not_ex_dict.values() and test_case_unsplit not in executed_name_off:
                executed_name_off.append(test_case_unsplit)
            else:
                if test_case_unsplit not in jama_test_plan_but_not_in_executed:
                    jama_test_plan_but_not_in_executed_from_dict.append(test_case_unsplit)

    return executed_but_not_in_jama_test_plan_from_dict, jama_test_plan_but_not_in_executed_from_dict, executed_name_off, in_jama_name_off


def update_jama_with_results(jama_client, jama_project, jama_test_plan, report_id,
                             jama_test_cycle, test_version_and_release_candidate, bulk_comment, test_results, compare):
    """
    Updates Jama with the test case results and returns the delta

    Args:
        jama_client: An initialized jama client object made from the JamaClientHelper
        jama_project: A string representing the Jama project that the test runs live in
        jama_test_plan: A string representing the name of the Jama test plan
        report_id: A string representing the report ID that is associated with this test plan
        jama_test_cycle: A string representing the cycle that is being tested
        test_version_and_release_candidate: A string representing the Jama test version and release candidate associated
        bulk_comment: A string representing the comment that the user provided to add to the test runs
        test_results: A list of test result objects
        compare: A bool if set to True do not update test run
    """
    # Retrieve the jama user ID of the current user (jama API credentials)
    user_jama_id, user_full_name = jama_client.get_current_user_id()

    # Get the project id and test plan
    project_id = jama_client.get_project_id(jama_project)
    test_plan_id = jama_client.get_test_plan_id(project_id, jama_test_plan)

    # Get the test cycle
    test_cycle_id = jama_client.get_test_cycle_id(test_plan_id, jama_test_cycle)

    # # Check that the jama test plan and jama test cycle have the report ID and version with the release candidate
    check_report_id_in_test_plan(report_id, jama_test_plan, compare)
    check_version_in_test_cycle(test_version_and_release_candidate, jama_test_cycle)

    # Get the test runs and the test cases needed to update from Jama
    test_runs = jama_client.get_test_runs(test_cycle_id)

    # Go through the test runs and create two dicts:
    #   jama_test_runs: a dict that maps a test run id to the test run data
    #   jama_test_case_to_test_run_ids: a dict that maps a test case ids to test run ids
    jama_test_runs = {}
    jama_test_case_to_test_run_ids = {}
    for test_run in test_runs:
        jama_test_runs[test_run['id']] = test_run
        jama_test_case_to_test_run_ids[test_run['fields']['testCase']] = test_run['id']

    # Go through the actual executed test results and create two lists:
    #   executed_test_results: a list of test run ids that were actually executed
    #   executed_but_not_in_jama_test_plan: a list of test case names of cases that were executed but are NOT in Jama
    executed_and_in_jama = []
    executed_but_not_in_jama_test_plan = []
    jama_test_plan_but_not_in_executed = []
    executed_test_results = []
    for test_result in test_results:
        if test_result.get_jama_test_case_id() in jama_test_case_to_test_run_ids.keys():
            jama_run_id = jama_test_case_to_test_run_ids[test_result.get_jama_test_case_id()]
            test_result.set_jama_test_run_id(jama_run_id)
            executed_test_results.append(jama_run_id)
        else:
            jama_test_plan_but_not_in_executed.append(test_result.get_name())

    # Go through the difference in test cases that were in Jama but not executed and create a list
    for test_run_id in (jama_test_runs.keys() - executed_test_results):
        
        executed_but_not_in_jama_test_plan.append(jama_test_runs[test_run_id]['fields']['name'])

    # Get the similarities between the list of test cases that were executed vs what is in Jama
    test_results_to_update = executed_test_results & jama_test_runs.keys()

    # Get list of test cases that were executed and in test plan
    if compare:
        for test_result in test_results_to_update:
            executed_and_in_jama.append(jama_test_runs[test_result]['fields']['name'])

    print()  # Spacer

    # Go through the test results again and push the result to Jama if the test case is in Jama
    for test_result in test_results:
        if test_result.get_jama_test_run_id() in test_results_to_update:
            if bulk_comment:
                test_result.set_bulk_comment(user_full_name, bulk_comment)
            if not compare:
                jama_client.update_test_run(jama_test_runs[test_result.get_jama_test_run_id()],
                                            test_result.get_jama_result(),
                                            test_result.get_jama_result_message(),
                                            test_result.get_runtime(), user_jama_id, bulk_comment)

    executed_but_not_in_jama_test_plan, jama_test_plan_but_not_in_executed, executed_name_off, in_jama_name_off = find_similar_test_cases_executed_in_plan(executed_but_not_in_jama_test_plan, jama_test_plan_but_not_in_executed, compare)
    # return the delta
    return executed_but_not_in_jama_test_plan, jama_test_plan_but_not_in_executed, executed_and_in_jama, executed_name_off, in_jama_name_off


def execute_jama_exec(commands):
    # Parse the arguments
    parsed_args = parse_args(commands)
    
    with open(os.path.join(parsed_args.config_path, parsed_args.config_file), 'r') as file:
        config = json.load(file)

    # Initialize the Jama client to interface with Jama APIs
    this_jama_client = initialize_jama_client(parsed_args.username, parsed_args.password, config)

    # Read the results output
    test_result_list = read_output_and_format(this_jama_client, config['jama_project'],
                                              config['path_to_test_results'], config['test_results_type'], config['jama_test_plan'], config, parsed_args.compare)

    # Push results to Jama and retrieve the delta
    executed_delta, jama_delta, executed_and_in_jama, executed_name_off, in_jama_name_off = update_jama_with_results(this_jama_client, config['jama_project'],
                                                                                                            config['jama_test_plan'],
                                                                                                            config['report_id'],
                                                                                                            config['jama_test_cycle'],
                                                                                                            config['test_version_and_release_candidate'],
                                                                                                            config['bulk_comment'],
                                                                                                            test_result_list,
                                                                                                            parsed_args.compare)

    # Report the test case delta to user
    notify_user_of_deltas(executed_delta, jama_delta, executed_and_in_jama, executed_name_off, in_jama_name_off, parsed_args.compare, os.path.dirname(parsed_args.config_path))


if __name__ == "__main__":
    execute_jama_exec(sys.argv[1:])
