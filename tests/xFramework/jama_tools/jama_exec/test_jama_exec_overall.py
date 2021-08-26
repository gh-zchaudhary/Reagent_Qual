#!/usr/bin/env python
#test_jama_exec_overall.py

import pytest
import os
import json
import jama_exec


@pytest.mark.parametrize("type, compare", 
                        [("robot", True),
                         ("pytest", True),
                         ("edge", True),
                         ("robot", False)])
def test_jama_exec_robot(type, compare):
    """Test that Jama Exec run successfully and output the anticipated results"""
    
    baseline_file = f"jama_exec_{type}.log"
    baseline_path = os.path.join(os.path.dirname(__file__), 'test_data', 'baseline', baseline_file)
    with open(baseline_path, 'r') as b:
        baseline = b.readlines()

    
    config_file = f"config_{type}.json"
    config_path = os.path.join(os.path.dirname(__file__), 'test_data', 'jama_exec_test_cases')
    
    username = os.environ.get('JAMA_USER')
    password = os.environ.get('JAMA_PASS')

    commands = [f"--username={username}", 
                f"--password={password}",
                f"--config_file={config_file}",
                f"--config_path={config_path}"]
    if compare:
        commands.append('--compare')

    jama_exec.execute_jama_exec(commands)

    if compare:
        output_path = os.path.join(os.path.dirname(__file__), 'test_data', "jama_exec.log")
        with open(output_path, 'r') as o:
            output = o.readlines()
        baseline_lines = len(baseline)
        output_lines = len(output)
        assert baseline_lines == output_lines, f"Baseline has {baseline_lines} and Output has {output_lines}"

        for i in range(baseline_lines):
            assert baseline[i] == output[i], f"Baseline is not equal to output {baseline[i]} {output[i]}"
