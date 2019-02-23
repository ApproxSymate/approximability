import re
import numpy as np
import random
import math
import ctypes
import cinpy
from pathlib import Path

from collections import OrderedDict

def check_approximability_of_expressions_var(q, exp, approximable_input, pc_with_error_func, path_condition_with_error, input_error_repeat, math_calls):
    is_var_approximable = 0
    average_sensitivy = 0.0
    path_with_error_satisfied = 0
    random.seed(a=0)

    input_approximability = []
    for var in approximable_input:
        input_approximability.append(0)

    for idx, var in enumerate(approximable_input):
        var_with_err_name = var + "_err"
        result = []

        for x in range(input_error_repeat):
            input_error = random.uniform(0.0, 1.0)
            exec("%s = %f" % (var_with_err_name, input_error), None, globals())
            error_added_string = var_with_err_name + " = " + str(input_error) + ";"
            error_added_string = pc_with_error_func + error_added_string

            if(len(math_calls)):
                math_call_error_string = handle_error_in_math_calls(math_calls)
                error_added_string += math_call_error_string

            pc_func_string = error_added_string + ("\nint answer = " + path_condition_with_error + ";\nreturn answer;}")

            #check if path condition with error is satisfied
            path_condition_with_error_true = 0
            if(path_condition_with_error == ''):
                path_with_error_satisfied = 1
                path_condition_with_error_true = 1
            else:
                func_with_error = cinpy.defc("with_error", ctypes.CFUNCTYPE(ctypes.c_int), pc_func_string)
                if(func_with_error()):
                    path_with_error_satisfied = 1
                    path_condition_with_error_true = 1

            if(path_condition_with_error_true):
                #get the error exp result
                if(exp[2] == '0'):
                    input_approximability[idx] += input_error_repeat
                    output_error = 0
                    break
                else:
                    input_approximability[idx] += 1
                    exp_string = sanitize_klee_expression(exp[2])
                    temp_string = ("\nfloat answer = " + exp_string + ";\nreturn answer;}")
                    func_string = error_added_string + temp_string
                    #change the return type to float (instead of int)
                    final_temp_string = "float " + func_string.split(' ', 1)[1]
                    try:
                        exp_func = cinpy.defc("with_error", ctypes.CFUNCTYPE(ctypes.c_float), final_temp_string)
                        output_error = exp_func()
                        result.append((input_error, output_error))
                    except Exception as e:
                        print("2 " + str(e))
                        print(exp[0] + ' ' + exp[1])
                        #print("Exception occured in eval (2)")
                        continue;
            else:
                continue

        approximable_result = check_approximability_of_result(result)
        average_sensitivy += approximable_result[0]
        is_var_approximable = approximable_result[1]

    q.put((exp[0], exp[1], is_var_approximable, average_sensitivy, path_with_error_satisfied, input_approximability))

def print_approximability_output(approximable_input, non_approximable_input, approximable_var, non_approximable_var, input_approximability_count, source_path, expression_count, input_error_repeat):
    approximable_output_strings = []
    non_approximable_output_strings = []
    get_var_names(approximable_output_strings, non_approximable_output_strings, approximable_var, non_approximable_var, source_path)

    # Print out the approximable and non-approximable variables
    print("\nApproximable variables (in increasing order of sensitivity)\n================================")
    for var in approximable_input:
        print(var.strip(",") + " (input)")
    for var in approximable_output_strings:
        print(var)

    print("\nNon-approximable variables (in increasing order of sensitivity)\n================================")
    for var in non_approximable_input:
        print(var.strip(",") + " (input)")
    for var in non_approximable_output_strings:
        print(var)

    # Print the approximability of inputs
    print("\nApproximability of input variables\n================================")
    for idx, var in enumerate(approximable_input):
        print(var + ' : %f%%' % ((input_approximability_count[idx] / (expression_count * input_error_repeat)) * 100))

    return

def get_var_names(approximable_output_strings, non_approximable_output_strings, approximable_var, non_approximable_var, source_path):
    approx_var = set()
    non_approx_var = set()
    for var in approximable_var:
        name_to_append = get_var_name_from_source(var[1], source_path)
        if(name_to_append != ''):
            if(name_to_append not in approx_var):
                approximable_output_strings.append(name_to_append)
                approx_var.add(name_to_append)
    for var in non_approximable_var:
        name_to_append = get_var_name_from_source(var[1], source_path)
        if(var[2]):
            if(name_to_append not in non_approx_var):
                non_approximable_output_strings.append(name_to_append)
                non_approx_var.add(name_to_append)
        else:
            if(name_to_append not in non_approx_var):
                non_approximable_output_strings.append(name_to_append + " (Error path not satisifed)")
                non_approx_var.add(name_to_append)
    return

def get_approximable_and_non_approximable_vars(approximable_var, non_approximable_var, results, approximable_input_size):
    input_approximability_count = []
    for x in range(approximable_input_size):
        input_approximability_count.append(0)

    for result in results:
        if(result[2]):
            approximable_var.append((result[3] / approximable_input_size, result[0], result[4]))
        else:
            non_approximable_var.append((result[3] / approximable_input_size, result[0], result[4]))

        input_approximability_count = [x + y for x, y in zip(input_approximability_count, result[5])]
    return input_approximability_count

def check_approximability_of_result(result):
    is_var_approximable = 0
    if(len(result)):
        result = sorted(result, key=lambda x: x[0])
        list_x, list_y = zip(*result)

        # linear reqression code from https://www.geeksforgeeks.org/linear-regression-python-implementation/
        xdata = np.array(list_x)
        ydata = np.array(list_y)
        n = np.size(xdata)
        m_x, m_y = np.mean(xdata), np.mean(ydata)
        SS_xy = np.sum(ydata * xdata - n * m_y * m_x)
        SS_xx = np.sum(xdata * xdata - n * m_x * m_x)
        if(abs(SS_xx) == 0.0):
            b_1 = 0
        else:
            b_1 = SS_xy / SS_xx

        # If gradient > 50% mark as non-approximable, else continue for other variables in the expression
        average_sensitivy = b_1
        # The test value is 1.1 instead of 1 because sometimes floats are slightly greater than 1 (example 1.0000000770289357)
        if(b_1 <= 1.1):
            is_var_approximable = 1

        return (average_sensitivy, is_var_approximable)
    else:
        return (0.0, is_var_approximable)

def handle_error_in_math_calls(math_calls):
    return_string = ""
    for args in math_calls:
        #get the argument value
        try:
            input_error_arg = eval(args[4], None, globals())
        except:
            input_error_arg = 0

        # evaluate the math call variable
        if(args[0] == "round"):
            exec("%s = round(%f*(1 - %f))" % ("error_result", eval(args[1]), input_error_arg), None, globals())
        else:
            if(args[0] == "sqrt" and (1 - input_error_arg) < 0):
                continue;
            else:
                exec("%s = math.%s(%f*(1 - %f))" % ("error_result", args[0], eval(args[1]), input_error_arg), None, globals())

        # evaluate the math call variable error
        if(eval(args[1]) != 0):
            exec("%s = abs((%s - %s)/%s)" % (args[2], error_result, args[1], args[1]), None, globals())
        else:
            exec("%s = abs((%s - %s)/1 + %s)" % (args[2], error_result, args[1], args[1]), None, globals())
        return_string += ("float " + args[2] + "=" + str(eval(args[2])) + ";")
    return return_string

def read_result_expressions(result_path, selected_path_id, expressions):
    with open(result_path + "/" + "test" + "{:0>6}".format(str(selected_path_id)) + '.expressions', 'r') as infile:
        for line in infile:
            method_name_line_tokens = line.split()
            if(len(method_name_line_tokens) > 0 and method_name_line_tokens[1] == 'Line'):
                method_name = method_name_line_tokens[5].rstrip(',')

                next_line = infile.readline()

                # read and sanitize expression
                exp = next_line.strip("\n")
                exp = exp.replace(">> 0", "")

                identifying_string = ''
                if(method_name_line_tokens[2] == "0"):
                    identifying_string = '0 ' + method_name_line_tokens[6] + ' ' + method_name
                else:
                    identifying_string = method_name_line_tokens[2] + ' ' + method_name

                expressions.append((identifying_string, method_name, exp))
    return

def get_approximable_input_func_error_string(approximable_input):
    output_string = ""
    for temp_var in approximable_input:
        var_with_err_name = temp_var + "_err"
        output_string += "float " + var_with_err_name + " = " + str(0.0) + ";"
        exec("%s = %f" % (var_with_err_name, 0.0), None, globals())
    return output_string

def get_math_call_string(result_path, selected_path_id, math_calls):
    exec("scaling = 1.0", None, globals())
    math_call_string = ""
    if(Path(result_path + "/" + "test" + "{:0>6}".format(str(selected_path_id)) + '.mathf').exists()):
        with open(result_path + "/" + "test" + "{:0>6}".format(str(selected_path_id)) + '.mathf', 'r') as infile:
            for line in infile:
                # Read function name
                func_name = line.split('_')[0];
                math_call_result_var = line.strip('\n')
                math_call_result_error_var = math_call_result_var + "_err"

                # Read the arg
                # Note: Because all of the functions that we're concerned take only one arg, for now we just handle one for now
                next_line = infile.readline()
                math_call_arg = next_line.split(',')[0]
                math_call_arg_err = next_line.split(',')[1].strip(' ')

                #sanitize math expressions
                math_call_arg_err = sanitize_klee_expression(math_call_arg_err)

                infile.readline()
                math_calls.append((func_name, math_call_result_var, math_call_result_error_var, math_call_arg, math_call_arg_err))
                input_arg = eval(math_call_arg, None, globals())
                if(func_name == "round"):
                    exec("%s = round(%f)" % (math_call_result_var, input_arg), None, globals())
                else:
                    exec("%s = math.%s(%f)" % (math_call_result_var, func_name, input_arg), None, globals())
                math_call_string += ("float " + math_call_result_var + "=" + str(eval(math_call_result_var))) + ";"

    return math_call_string

def get_func_string_for_inputs(input_variables, arrays, largest_index, array_inputs, regular_inputs):
    input_string = ""
    #array delcarations
    for array in arrays:
        declared_size = 0
        for input in input_variables:
            if(input[1] == array):
                declared_size = input[3]
                break
        if(int(declared_size) > int(largest_index[array])):
            input_string += "float " + array + "[" + str(declared_size) + "];"
        else:
            input_string += "float " + array + "[" + str(largest_index[array]) + "];"
    #array inputs
    for array_input in array_inputs:
        input_string += str(array_input[0]) + "[" + str(array_input[1]) + "] = " + str(array_input[2]) + ";"
    #regular inputs
    for regular_input in regular_inputs:
        input_string += "float " + str(regular_input[0]) + " = " + str(regular_input[1]) + ";"
    return input_string

def execute_input(arrays, array_inputs, regular_inputs):
    for array in arrays:
        exec("%s = []" % (array), None, globals())
    for array_input in array_inputs:
        exec("%s.insert(%d, %d)" % (array_input[0], array_input[1], array_input[2]), None, globals())
    for regular_input in regular_inputs:
        exec("%s = %d" % (regular_input[0], regular_input[1]), None, globals())

def read_input(selected_path_id, input_path, largest_index, arrays, array_inputs, regular_inputs):
    if(not input_path == ''):
        try:
            input_file = open(input_path + "/" + "input_" + selected_path_id + ".txt", "r")
        except:
            try:
                # Use default input file if we could not open the path-specific input file
                input_file = open(input_path + "/" + "input.txt", "r")
            except:
                print("Cannot open input file: " + input_path + "/" + "input.txt")
                quit()


    print("\nInput values\n================================")
    for line in input_file:
        tokens = line.split('=')
        variable_name = tokens[0].split('[')[0].strip()
        #array inputs
        if('[' in tokens[0] and ']' in tokens[0]):
            arrays.add(variable_name)
            value = float(tokens[1].strip())
            print("%s = %f" % (tokens[0].strip(), value))
            current_index = int(tokens[0].split('[')[1].split(']')[0].strip())
            array_inputs.append((variable_name, current_index, value))
            #need to keep track of largest index to make a declaration with sufficient elements
            #this assumes that the array indices are in ascending order in the input file for a given input
            largest_index[variable_name] = current_index
        else:
            variable_name = tokens[0].strip()
            value = float(tokens[1].strip())
            print("%s = %f" % (variable_name, value))
            regular_inputs.append((variable_name, value))

    input_file.close()
    return

def get_var_name_from_source(var_line, source_path):
    tokens = var_line.split(' ')
    if(tokens[0] == "0"):
        return tokens[1].strip(',') + " " + tokens[2]

    var_name = ""
    fp = open(source_path)
    for i, line in enumerate(fp):
        if((i + 1) == int(tokens[0])):
            # print(var_line)
            # print(line)
            if('for (' in line):
                line_tokens = line.split(';');
                characters = list(line_tokens[2])
                for letter in characters:
                    if(letter == '+' or letter == '-' or letter == '*' or letter == '/'):
                        break;
                    else:
                        var_name += letter;
                var_name = var_name.strip()
            elif('memcpy' in line):
                var_name = line.split(',')[0]
                var_name = var_name.split('(')[1].strip()
            elif('+=' in line or "-=" in line or '/=' in line or '*=' in line):
                line_tokens = line.split('=');
                characters = list(line_tokens[0])
                for letter in characters:
                    if(letter == '+' or letter == '-' or letter == '*' or letter == '/' or letter == '['):
                        break;
                    else:
                        var_name += letter;
                var_name = var_name.strip()
            elif('=' in line):
                var_name = line.split('=')[0].strip(';').strip('\t')
                if('[' in var_name):
                    var_name = var_name.split('[')[0].strip()
                else:
                    var_name = var_name.split(' ')[-2].strip('(')
            elif('klee_bound_error' in line):
                var_name = line.split(',')[1].lstrip().replace('"', '')
            elif('return' in line):
                return ''
            else:
                var_name = line.strip('\t').split(' ')
                if(len(var_name) > 1):
                    var_name = var_name[1].strip('\n').strip(';')
                else:
                    var_name = var_name[0].strip('\n').strip(';')
    #print(var_name + " " + var_line)

    return var_name + " " + tokens[1]

def get_input_variables(input_variables, source_path):
    source = open(source_path, "r")
    for line in source:
        if re.match("(.*)klee_make_symbolic(.*)", line):
            tokens = re.split(r'[(|)]|\"', line)
            if('arr' in tokens[4]):
                temp = tokens[4].split('_')
                tokens[4] = temp[-1]
                tokens[3] = tokens[3].split('*')[-1].replace(',','').strip()
                input_variables.append((tokens[2], tokens[4], 1, tokens[3]))
            else:
                input_variables.append((tokens[2], tokens[4], 0, ''))
            print(tokens[4])
    source.close()
    return

def get_input_error_variables(approximable_input, source_path):
    source = open(source_path, "r")
    for line in source:
        if re.match("(.*)klee_track_error(.*)", line):
            tokens = re.split(r'[(|)]|\"|&|,', line)
            name = tokens[-3].split('_')[0]
            approximable_input.append(name)
            print(name)
    source.close()
    return

def sanitize_klee_expression(path_condition):
    path_condition = path_condition.replace(" = ", " == ")
    path_condition = path_condition.replace(">> 0", "")
    path_condition = path_condition.replace(">> ", ">> (int)")
    path_condition = path_condition.replace("<< ", "<< (int)")
    path_condition = path_condition.replace("true", "1");
    path_condition = path_condition.replace("false", "0");
    return path_condition
