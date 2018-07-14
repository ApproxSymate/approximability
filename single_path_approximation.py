import subprocess
import re
import os
import random
import numpy as np
import path
import sys
import ctypes
import cinpy

from common import get_var_name_from_source

def approximate_for_single_path(result_path, source_path, input_path, ktest_tool_path):
    print("Source: " + source_path)
    print("Output: " + result_path + "\n")

    # Find the path longest path with the highest probabilty
    # In case there are more than one, just pick one
    depth = []
    prob = []
    index = []
    exec("scaling = 1.0", None, globals())
    input_error_repeat = 10
    random.seed(0)
    for root, dirs, files in os.walk(result_path):
        for filename in files:
            if filename.endswith(".prob"):
                with open(result_path + filename, 'r') as fin:
                    firstline = fin.readline().split(",")
                    index.append(firstline[2].strip())
                    secondline = fin.readline().split(",")
                    depth.append(secondline[0])
                    prob.append(float(secondline[1]))

    #print(prob)
    max_depth = max(depth)
    max_probabilities = []
    max_probabilities_index = []
    for idx, val in enumerate(depth):
        if val == max_depth:
            max_probabilities.append(prob[idx])
            max_probabilities_index.append(index[idx])

    selected_path_id = max_probabilities_index[max_probabilities.index(max(max_probabilities))]
    #selected_path_id = '23' - floodfill
    #selected_path_id = '11' - raytracer
    print("Selected path #:" + selected_path_id + "\n")

    # Get the input variables and their types and mark those for which error is tracked
    # TODO: Handle floats converted to ints (we only need to do this handling if the conversion happened in the input)
    print("Input variables\n================================")
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
            print(tokens[4])
    source.close()

    print("\nInput with error\n================================")
    source = open(source_path, "r")
    approximable_input = []
    for line in source:
        if re.match("(.*)klee_track_error(.*)", line):
            tokens = re.split(r'[(|)]|\"|&|,', line)
            name = tokens[-3].split('_')[0]
            approximable_input.append(name)
            print(name)
    source.close()

    # Get the path condition with error for the selected path
    source = open(result_path + "test" + "{:0>6}".format(str(selected_path_id)) + ".kquery_precision_error", "r")
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
    print("\nInput values\n================================")
    result = subprocess.run([ktest_tool_path, '--write-ints', result_path + "test" + "{:0>6}".format(str(selected_path_id)) + '.ktest'], stdout=subprocess.PIPE)
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
                print("%s = %f" % (tokens[idx + 3].strip().replace("'", ""), float(tokens[idx + 9].strip())))
            pc_without_error_func_definitions += tokens[idx + 3].strip().replace("'", "") + " = " + str(tokens[idx + 9].strip()) + ";"
        idx += 9

    #load pre-defined input in file (used mainly for floating point constants)
    largest_index = dict()
    if(not input_path == ''):
        try:
            input_file = open(input_path + "input_" + selected_path_id + ".txt", "r")
        except:
            try:
                # Use default input file if we could not open the path-specific input file
                input_file = open(input_path + "input.txt", "r")
            except:
                print("Cannot open input file")
                quit()

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
                print("%s = %f" % (tokens[0].strip(), float(tokens[1].strip())))
                pc_without_error_func_definitions += tokens[0].strip() + " = " + tokens[1].strip() + ";"
                largest_index[variable_name] = int(tokens[0].split('[')[1].split(']')[0].strip())
            else:
                variable_name = tokens[0].strip()
                exec("%s = %f" % (tokens[0].strip(), float(tokens[1].strip())), None, globals())
                print("%s = %f" % (tokens[0].strip(), float(tokens[1].strip())))
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
        
    pc_with_error_func = pc_without_error_func
    pc_without_error_func += "\nfloat answer = " + path_condition_without_error + ";\nreturn answer;}"
    #Check if path condition without error is satisfied with the input
    #Cannot check this because python doesn't have integer division as implemented in C!!! argh!!!!!
    if(not path_condition_without_error == ""):
        func_without_error = cinpy.defc("without_error", ctypes.CFUNCTYPE(ctypes.c_int), pc_without_error_func)
        if(func_without_error()):
            print("\nInput values satisfies path condition without error...")
        else:
            print("\nInput values do not satisfy path condition without error...")
    else:
        print("\nInput values satisfies path condition without error...")

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
    with open(result_path + "test" + "{:0>6}".format(str(selected_path_id)) + '.expressions', 'r') as infile:
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
                    for x in range(input_error_repeat):
                        # Generate a random error value in (0,1) for the concerned variable
                        var_with_err_name = var + "_err"
                        input_error = random.uniform(0.0, 1.0)
                        exec("%s = %f" % (var_with_err_name, input_error), None, globals())
                        error_added_string = var_with_err_name + " = " + str(input_error) + ";"
                        function_string = pc_with_error_func + error_added_string + "\nfloat answer = " + path_condition_with_error + ";\nreturn answer;}"

                        # Check if path condition with error is satisfied
                        if(path_condition_with_error == ''):
                            path_with_error_satisfied = 1
                            if(exp == '0'):
                                input_approximability_count[idx] += input_error_repeat
                                break
                            else:
                                input_approximability_count[idx] += 1
                                try:
                                    output_error = eval(exp, None, globals())
                                    result.append((input_error, output_error))
                                except:
                                    continue;
                        else:
                            func_with_error = cinpy.defc("without_error", ctypes.CFUNCTYPE(ctypes.c_int), function_string)
                            if(func_with_error()):
                                # If satisfied, get the output error from expression
                                path_with_error_satisfied = 1
                                input_approximability_count[idx] += 1
                                if(exp == '0'):
                                    break
                                else:
                                    try:
                                        output_error = eval(exp, None, globals())
                                        result.append((input_error, output_error))
                                    except:
                                        continue;

                    if(len(result)):
                        # Check for monotonicity of output error. If not monotonous continue to evaluate other inputs.
                        result = sorted(result, key=lambda x: x[0])
                        monotonous_count = 0
                        for index, item in enumerate(result):
                            if(index < (len(result) - 1) and item[1] <= result[index + 1][1]):
                                monotonous_count += 1

                        # If at least 90% monotonous, get the linear regression gradient
                        if((monotonous_count / (len(result) - 1)) >= 0.8):
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
                if(is_var_approximable):
                    approximable_var.append(((average_sensitivy / len(approximable_input)), method_name_line_tokens[2] + ' ' + method_name))
                else:
                    non_approximable_var.append(((average_sensitivy / len(approximable_input)), method_name_line_tokens[2] + ' ' + method_name, path_with_error_satisfied))
            else:
                continue

    # Get the non-approximable input
    non_approximable_input = list(set([x[1] for x in input_variables]) - set(approximable_input))

    #Sort by average sensitivity
    approximable_var.sort(key=lambda tup: tup[0], reverse=True)
    non_approximable_var.sort(key=lambda tup: tup[0], reverse=True)
    #for item in approximable_var:
        #print(item[0])
        #print(self.get_var_name_from_source(item[1], source_path) + "\n")
    #print(non_approximable_var)

    approximable_output_strings = []
    non_approximable_output_strings = []
    for var in approximable_var:
        approximable_output_strings.append(get_var_name_from_source(var[1], source_path))
    for var in non_approximable_var:
        if(var[2]):
            non_approximable_output_strings.append(get_var_name_from_source(var[1], source_path))
        else:
            non_approximable_output_strings.append(get_var_name_from_source(var[1], source_path) + " (Error path not satisifed)")
    #Remove duplicates
    approximable_output_strings = list(set(approximable_output_strings))
    non_approximable_output_strings = list(set(non_approximable_output_strings))

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
        print(var + ' : %d%%' % ((input_approximability_count[idx] / (expression_count * input_error_repeat)) * 100))
