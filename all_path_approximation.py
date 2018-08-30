import subprocess
import re
import os
import random
import numpy as np
import path
import sys
import ctypes
import cinpy
import math
from pathlib import Path
import faulthandler

from common import get_var_name_from_source

def approximate_for_all_paths(result_path, source_path, input_path, ktest_tool_path):
    print("Source: " + source_path)
    print("Output: " + result_path + "\n")
    faulthandler.enable()

    input_error_repeat = 10
    exec("scaling = 1.0", None, globals())

    # Get the input variables and their types and mark those for which error is tracked
    # TODO: Handle floats converted to ints (we only need to do this handling if the conversion happened in the input)
    var_string ="Input variables\n================================\n"
    source = open(source_path, "r")
    input_variables = []
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
            var_string +=(tokens[4] + "\n")
    source.close()

    var_string +=("\nInput with error\n================================\n")
    source = open(source_path, "r")
    approximable_input = []
    for line in source:
        if re.match("(.*)klee_track_error(.*)", line):
            tokens = re.split(r'[(|)]|\"|&|,', line)
            name = tokens[-3].split('_')[0]
            approximable_input.append(name)
            var_string +=(name + "\n")
    source.close()

    #Iterate over all paths
    paths = []
    for root, dirs, files in os.walk(result_path):
        for filename in files:
            if filename.endswith(".prob"):
                with open(result_path + "/" + filename, 'r') as fin:
                    paths.append(fin.readline().split(",")[2].strip())

    for p in paths:
        selected_path_id = p
        print("Selected path #:" + selected_path_id)
        out_string =("Selected path #:" + selected_path_id + "\n\n") + var_string

        # Get the path condition with error for the selected path
        source = open(result_path + "/" + "test" + "{:0>6}".format(str(selected_path_id)) + ".kquery_precision_error", "r")
        path_condition_with_error = source.readline().rstrip("\n\r")
        path_condition_without_error = source.readline().rstrip("\n\r")
        source.close()
        if(not path_condition_with_error == ' '):
            path_condition_with_error = path_condition_with_error.replace(" = ", " == ")
            path_condition_with_error = path_condition_with_error.replace(">> 0", "")
            path_condition_with_error = path_condition_with_error.replace(">> ", ">> (int)")
            path_condition_with_error = path_condition_with_error.replace("<< ", "<< (int)")
            path_condition_with_error = path_condition_with_error.replace("true", "1");
            path_condition_with_error = path_condition_with_error.replace("false", "0");
        if(not path_condition_without_error == ' '):
            path_condition_without_error = path_condition_without_error.replace(" = ", " == ")
            path_condition_without_error = path_condition_without_error.replace(">> 0", "")
            path_condition_without_error = path_condition_without_error.replace(">> ", ">> (int)")
            path_condition_without_error = path_condition_without_error.replace("<< ", "<< (int)")
            path_condition_without_error = path_condition_without_error.replace("true", "1");
            path_condition_without_error = path_condition_without_error.replace("false", "0");

        #build C function to check satisfiability of path conditions with and without error
        pc_without_error_func = "int without_error() {\n float scaling = 1.0;"
        pc_without_error_func_declarations = dict()
        for var in input_variables:
            if(var[2] == 0):
                pc_without_error_func_declarations[var[1]] = 0
            else:
                pc_without_error_func_declarations[var[1]] = int(var[3])

        pc_without_error_func_definitions = ""

        # get an input, for which the path condition (without error) is satisfied
        out_string +=("\nInput values\n================================\n")
        result = subprocess.run([ktest_tool_path, '--write-ints', result_path + "/" + "test" + "{:0>6}".format(str(selected_path_id)) + '.ktest'], stdout=subprocess.PIPE)
        output_string = result.stdout.decode('utf-8')
        tokens = re.split(r'\n|:', output_string)
        idx = 5
        num_args = int(tokens[idx].strip())
        for args in range(num_args):
            temp = tokens[idx + 3].strip().replace("'", "")
            if('arr' in temp):
                exec("%s = []" % temp.split('_')[-1].strip(), None, globals())
            else:
                exec("%s = %f" % (tokens[idx + 3].strip().replace("'", ""), float(tokens[idx + 9].strip())), None, globals())
                #if the inputs are zero, then the expressions will not work because they use relative error
                if(not float(tokens[idx + 9].strip()) == 0.0):
                    out_string +=("%s = %f" % (tokens[idx + 3].strip().replace("'", ""), float(tokens[idx + 9].strip())) + "\n")
                pc_without_error_func_definitions += tokens[idx + 3].strip().replace("'", "") + " = " + str(tokens[idx + 9].strip()) + ";"
            idx += 9

        #load pre-defined input in file (used mainly for floating point constants)
        largest_index = dict()
        if(not input_path == ''):
            try:
                input_file = open(input_path + "/" + "input_" + selected_path_id + ".txt", "r")
            except:
                try:
                    # Use default input file if we could not open the path-specific input file
                    input_file = open(input_path + "/" + "input.txt", "r")
                except:
                    out_string +=("Cannot open input file\n")
                    print("Cannot open input file for path #" + selected_path_id)
                    continue

            defined_variables = []
            c_defined_variables = []
            for line in input_file:
                tokens = line.split('=')
                variable_name = tokens[0].split('[')[0].strip()
                if not variable_name in defined_variables:
                    exec("%s = []" % (variable_name), None, globals())
                    defined_variables.append(variable_name)
                if('[' in tokens[0] and ']' in tokens[0]):
                    exec("%s.insert(%d, %f)" % (tokens[0].split('[')[0].strip(), int(tokens[0].split('[')[1].split(']')[0].strip()), float(tokens[1])), None, globals())
                    out_string +=("%s = %f" % (tokens[0].strip(), float(tokens[1].strip())) + "\n")
                    pc_without_error_func_definitions += tokens[0].strip() + " = " + tokens[1].strip() + ";"
                    largest_index[variable_name] = int(tokens[0].split('[')[1].split(']')[0].strip())
                else:
                    variable_name = tokens[0].strip()
                    exec("%s = %f" % (tokens[0].strip(), float(tokens[1].strip())), None, globals())
                    out_string +=("%s = %f" % (tokens[0].strip(), float(tokens[1].strip())) + "\n")
                    if variable_name in c_defined_variables:
                        pc_without_error_func_definitions += tokens[0].strip() + " = " + tokens[1].strip() + ";"
                    else:
                        if not variable_name in pc_without_error_func_declarations:
                            pc_without_error_func_definitions += "float "
                        pc_without_error_func_definitions += tokens[0].strip() + " = " + tokens[1].strip() + ";"
                        c_defined_variables.append(variable_name)
            input_file.close()

        for variable_name, num_elements in pc_without_error_func_declarations.items():
            if variable_name in largest_index:
                if num_elements < largest_index[variable_name]:
                    pc_without_error_func += "float " + variable_name + "[" + str(largest_index[variable_name] + 1) + "];\n"
                elif num_elements > 0:
                    pc_without_error_func += "float " + variable_name + "[" + str(num_elements) + "];\n"
                else:
                    pc_without_error_func += "float " + variable_name + ";\n"
            elif num_elements > 0:
                pc_without_error_func += "float " + variable_name + "[" + str(num_elements) + "];\n"
            else:
                pc_without_error_func += "float " + variable_name + ";\n"

        pc_without_error_func += pc_without_error_func_definitions

        #read math function calls
        math_calls_present = 0
        if(Path(result_path + "/" + "test" + "{:0>6}".format(str(selected_path_id)) + '.mathf').exists()):
            math_calls_present = 1
        if(math_calls_present):
            math_calls = []
            with open(result_path + "/" + "test" + "{:0>6}".format(str(selected_path_id)) + '.mathf', 'r') as infile:
                for line in infile:
                    # Read function name
                    func_name = line.split('_')[0];
                    math_call_result_var = line.strip('\n')
                    math_call_result_error_var = line.strip('\n') + "_err"

                    # Read the arg
                    # Note: Because all of the functions that we're concerned take only one arg, for now we just handle one for now
                    next_line = infile.readline()
                    math_call_arg = next_line.split(',')[0]
                    math_call_arg_err = next_line.split(',')[1].strip(' ')

                    #sanitize math expressions
                    math_call_arg_err = math_call_arg_err.replace(" = ", " == ")
                    math_call_arg_err = math_call_arg_err.replace(">> 0", "")
                    math_call_arg_err = math_call_arg_err.replace(">> ", ">> (int)")
                    math_call_arg_err = math_call_arg_err.replace("<< ", "<< (int)")
                    math_call_arg_err = math_call_arg_err.replace("true", "1");
                    math_call_arg_err = math_call_arg_err.replace("false", "0");

                    infile.readline()
                    math_calls.append((func_name, math_call_result_var, math_call_result_error_var, math_call_arg, math_call_arg_err))
                    input_arg = eval(math_call_arg, None, globals())
                    if(func_name == "round"):
                        exec("%s = round(%f)" % (math_call_result_var, input_arg), None, globals())
                    else:
                        exec("%s = math.%s(%f)" % (math_call_result_var, func_name, input_arg), None, globals())
                    pc_without_error_func += ("float " + math_call_result_var + "=" + str(eval(math_call_result_var))) + ";"

        pc_with_error_func = pc_without_error_func
        pc_without_error_func += "\nfloat answer = " + path_condition_without_error + ";\nreturn answer;}"
        #Check if path condition without error is satisfied with the input
        #Cannot check this in python because python doesn't have integer division as implemented in C!!! argh!!!!!
        if(not path_condition_without_error == ""):
            func_without_error = cinpy.defc("without_error", ctypes.CFUNCTYPE(ctypes.c_int), pc_without_error_func)
            if(func_without_error()):
                out_string +=("\nInput values satisfies path condition without error...\n")
            else:
                out_string +=("\nInput values do not satisfy path condition without error...\n")
        else:
            print("\nInput values satisfies path condition without error...\n")

        approximable_var = []
        non_approximable_var = []

        # Maintain a measure of the approximability of the input
        input_approximability_count = []
        for var in approximable_input:
            input_approximability_count.append(0)

        for temp_var in approximable_input:
            pc_with_error_func += "float " + temp_var + "_err" + " = " + str(0.0) + ";"

        # Read expression
        expression_count = 0
        with open(result_path + "/" + "test" + "{:0>6}".format(str(selected_path_id)) + '.expressions', 'r') as infile:
            for line in infile:
                method_name_line_tokens = line.split()
                if(len(method_name_line_tokens) > 0 and method_name_line_tokens[1] == 'Line'):
                    method_name = method_name_line_tokens[5].rstrip(',')

                    next_line = infile.readline()

                    tokens = next_line.split()

                    expression_count += 1
                    # read and sanitize expression
                    exp = next_line.strip("\n")
                    exp = exp.replace(">> 0", "")

                    is_var_approximable = 0
                    average_sensitivy = 0.0
                    path_with_error_satisfied = 0

                    # For each approximable input variable
                    for idx, var in enumerate(approximable_input):
                        # assign other variable errors to zero
                        for temp_var in approximable_input:
                            var_with_err_name = temp_var + "_err"
                            exec("%s = %f" % (var_with_err_name, 0.0), None, globals())

                        # for repeat
                        result = []
                        random.seed(a=0)
                        for x in range(input_error_repeat):
                            # Generate a random error value in (0,1) for the concerned variable
                            var_with_err_name = var + "_err"
                            input_error = random.uniform(0.0, 1.0)
                            exec("%s = %f" % (var_with_err_name, input_error), None, globals())
                            error_added_string = var_with_err_name + " = " + str(input_error) + ";"
                            function_string = pc_with_error_func + error_added_string

                            #evaluate math calls
                            if(math_calls_present):
                                for args in math_calls:
                                    #get the argument value
                                    try:
                                        input_error_arg = eval(args[4], None, globals())
                                    except:
                                        input_error_arg = 0

                                    if(args[0] == "round"):
                                        exec("%s = round(%f*(1 - %f))" % ("error_result", eval(args[1]), input_error_arg), None, globals())
                                    else:
                                        exec("%s = math.%s(%f*(1 - %f))" % ("error_result", args[0], eval(args[1]), input_error_arg), None, globals())

                                    if(eval(args[1]) != 0):
                                        exec("%s = abs((%s - %s)/%s)" % (args[2], error_result, args[1], args[1]), None, globals())
                                    else:
                                        exec("%s = abs((%s - %s)/1 + %s)" % (args[2], error_result, args[1], args[1]), None, globals())
                                    function_string += ("float " + args[2] + "=" + str(eval(args[2])) + ";")

                            function_string += ("\nfloat answer = " + path_condition_with_error + ";\nreturn answer;}")

                            # Check if path condition with error is satisfied
                            if(path_condition_with_error == ''):
                                path_with_error_satisfied = 1
                                if(exp == '0'):
                                    input_approximability_count[idx] += input_error_repeat
                                    output_error = 0
                                    break
                                else:
                                    input_approximability_count[idx] += 1
                                    try:
                                        output_error = eval(exp, None, globals())
                                        result.append((input_error, output_error))
                                    except:
                                        out_string +=("Exception occured in eval (1)\n")
                                        continue;
                            else:
                                func_with_error = cinpy.defc("without_error", ctypes.CFUNCTYPE(ctypes.c_int), function_string)
                                if(func_with_error()):
                                    # If satisfied, get the output error from expression
                                    path_with_error_satisfied = 1
                                    input_approximability_count[idx] += 1
                                    if(exp == '0'):
                                        output_error = 0
                                    else:
                                        try:
                                            output_error = eval(exp, None, globals())
                                            result.append((input_error, output_error))
                                        except:
                                            out_string +=("Exception occured in eval (2)\n")
                                            continue;

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
                            b_1 = SS_xy / SS_xx

                            # If gradient > 50% mark as non-approximable, else continue for other variables in the expression
                            average_sensitivy += b_1
                            # The test value is 1.1 instead of 1 because sometimes floats are slightly greater than 1 (example 1.0000000770289357)
                            if(b_1 <= 1.1):
                                is_var_approximable = 1

                    # If for at least one variable in the expression, the output is approximable, then add to approximable list.
                    # Else add to the non-approximable list
                    identifying_string = ''
                    if(method_name_line_tokens[2] == "0"):
                        identifying_string = '0 ' + method_name_line_tokens[6] + ' ' + method_name
                    else:
                        identifying_string = method_name_line_tokens[2] + ' ' + method_name

                    if(is_var_approximable):
                        approximable_var.append(((average_sensitivy / len(approximable_input)), identifying_string))
                    else:
                        non_approximable_var.append(((average_sensitivy / len(approximable_input)), identifying_string, path_with_error_satisfied))
                else:
                    continue

        # Get the non-approximable input
        non_approximable_input = list(set([x[1] for x in input_variables]) - set(approximable_input))

        #Sort by average sensitivity
        approximable_var.sort(key=lambda tup: tup[0], reverse=True)
        non_approximable_var.sort(key=lambda tup: tup[0], reverse=True)
        #for item in approximable_var:
            #print(itout_string +=)
            #print(self.get_var_name_from_source(item[1], source_path) + "\n")
        #print(non_approximable_var)

        approximable_output_strings = []
        non_approximable_output_strings = []
        for var in approximable_var:
            name_to_append = get_var_name_from_source(var[1], source_path)
            if(name_to_append != ''):
                approximable_output_strings.append(name_to_append)
        for var in non_approximable_var:
            if(var[2]):
                non_approximable_output_strings.append(get_var_name_from_source(var[1], source_path))
            else:
                non_approximable_output_strings.append(get_var_name_from_source(var[1], source_path) + " (Error path not satisifed)")
        #Remove duplicates
        approximable_output_strings = list(set(approximable_output_strings))
        non_approximable_output_strings = list(set(non_approximable_output_strings))

        # Print out the approximable and non-approximable variables
        out_string +=("\nApproximable variables (in increasing order of sensitivity)\n================================\n")
        for var in approximable_input:
            out_string +=(var.strip(",") + " (input)\n")
        for var in approximable_output_strings:
            out_string +=(var + "\n")

        out_string +=("\nNon-approximable variables (in increasing order of sensitivity)\n================================\n")
        for var in non_approximable_input:
            out_string +=(var.strip(",") + " (input)\n")
        for var in non_approximable_output_strings:
            out_string +=(var + "\n")

        # Print the approximability of inputs
        out_string +=("\nApproximability of input variables\n================================\n")
        for idx, var in enumerate(approximable_input):
            out_string +=(var + ' : %d%%\n' % ((input_approximability_count[idx] / (expression_count * input_error_repeat)) * 100))

        f = open(result_path + "/approximability_" + selected_path_id +".txt","w+")
        f.write(out_string)
        f.close()

        print("Path " + selected_path_id + " done.")
