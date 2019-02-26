import os
import ctypes
import cinpy

from multiprocessing import Process, Queue

from common import get_input_variables
from common import get_input_error_variables
from common import sanitize_klee_expression
from common import read_input
from common import execute_input
from common import get_func_string_for_inputs
from common import get_math_call_string
from common import get_approximable_input_func_error_string
from common import read_result_expressions
from common import check_approximability_of_expressions_var
from common import get_approximable_and_non_approximable_vars
from common import print_approximability_output

def approximate_for_single_path(result_path, source_path, input_path, ktest_tool_path, print_lines):
    print("Source: " + source_path)
    print("Output: " + result_path)

    #exec("scaling = 1.0", None, globals())
    input_error_repeat = 10
    print("input error repeat = %d\n" % input_error_repeat)

    selected_path_id = get_path_for_approximation(result_path);
    print("Selected path #:" + selected_path_id + "\n")

    # Get the input variables and their types and mark those for which error is tracked
    # TODO: Handle floats converted to ints (we only need to do this handling if the conversion happened in the input)
    print("Input variables\n================================")
    input_variables = []
    get_input_variables(input_variables, source_path);

    print("\nInput with error\n================================")
    approximable_input = []
    get_input_error_variables(approximable_input, source_path)

    #Read input
    largest_index = dict()
    arrays = set()
    regular_inputs = []
    array_inputs = []
    read_input(selected_path_id, input_path, largest_index, arrays, array_inputs, regular_inputs)

    #Execute inputs
    execute_input(arrays, array_inputs, regular_inputs)

    # Get the path condition with error for the selected path
    source = open(result_path + "/" + "test" + "{:0>6}".format(str(selected_path_id)) + ".kquery_precision_error", "r")
    path_condition_with_error = source.readline().rstrip("\n\r")
    path_condition_without_error = source.readline().rstrip("\n\r")
    source.close()
    if(not path_condition_with_error == ' '):
        path_condition_with_error = sanitize_klee_expression(path_condition_with_error)

    if(not path_condition_without_error == ' '):
        path_condition_without_error = sanitize_klee_expression(path_condition_without_error)

    #Form path condition checking functions in C with existing input
    input_string = get_func_string_for_inputs(input_variables, arrays, largest_index, array_inputs, regular_inputs)
    pc_without_error_func = "int without_error() {\n float scaling = 1.0; " + input_string
    pc_with_error_func = "int with_error() {\n float scaling = 1.0; " + input_string

    #handle math calls
    math_calls = []
    math_calls_func_string = get_math_call_string(result_path, selected_path_id, math_calls)
    pc_without_error_func += math_calls_func_string
    pc_with_error_func += math_calls_func_string

    #check if input satisfies path condition without error
    pc_without_error_func += "\nfloat answer = " + path_condition_without_error + ";\nreturn answer;}"
    if(not path_condition_without_error == ""):
        func_without_error = cinpy.defc("without_error", ctypes.CFUNCTYPE(ctypes.c_int), pc_without_error_func)
        if(func_without_error()):
            print("\nInput values satisfies path condition without error...")
        else:
            print("\nInput values do not satisfy path condition without error...")
    else:
        print("\nInput values satisfies path condition without error...")

    approximable_input_func_error_string = get_approximable_input_func_error_string(approximable_input)
    pc_with_error_func += approximable_input_func_error_string

    expressions = []
    read_result_expressions(result_path, selected_path_id, expressions)

    #check the approximability of each expression's variable
    q = Queue()
    results = []
    processes = []
    for idx, exp in enumerate(expressions):
        p = Process(target = check_approximability_of_expressions_var, args=(q, idx, exp, approximable_input, pc_with_error_func, path_condition_with_error, input_error_repeat, math_calls))
        p.start()
        processes.append(p)

    for p in processes:
        results.append(q.get())
        p.join()

    #organize results and calculate output
    approximable_var = []
    non_approximable_var = []
    # Maintain a measure of the approximability of the input
    input_approximability_count = get_approximable_and_non_approximable_vars(approximable_var, non_approximable_var, results, len(approximable_input))

    # Get the non-approximable input
    non_approximable_input = list(set([x[1] for x in input_variables]) - set(approximable_input))

    #Sort by average sensitivity
    approximable_var.sort(key=lambda tup: tup[0], reverse=True)
    non_approximable_var.sort(key=lambda tup: tup[0], reverse=True)

    print_approximability_output(approximable_input, non_approximable_input, approximable_var, non_approximable_var, input_approximability_count, source_path, len(expressions), input_error_repeat, print_lines)

def get_path_for_approximation(result_path):
    # Find the path longest path with the highest probabilty
    # In case there are more than one, just pick one
    depth = []
    prob = []
    index = []
    selected_path_id = '1'
    for root, dirs, files in os.walk(result_path):
        for filename in files:
            if filename.endswith(".prob"):
                with open(result_path + "/" + filename, 'r') as fin:
                    firstline = fin.readline().split(",")
                    index.append(firstline[2].strip())
                    secondline = fin.readline().split(",")
                    depth.append(int(secondline[0]))
                    prob.append(float(secondline[1]))

    if(len(depth) > 0):
        max_depth = max(depth)
        max_probabilities = []
        max_probabilities_index = []
        for idx, val in enumerate(depth):
            if val == max_depth:
                max_probabilities.append(prob[idx])
                max_probabilities_index.append(index[idx])
        selected_path_id = max_probabilities_index[max_probabilities.index(max(max_probabilities))]
    return selected_path_id
