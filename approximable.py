import re
import os
import subprocess
import random
import numpy as np
import path
import sys
import ctypes
import cinpy

class Approximable(object):

    def get_var_name_from_source(self, var_line, source_path):
        tokens = var_line.split(' ')
        var_name = ""
        fp = open(source_path)
        for i, line in enumerate(fp):
            if((i + 1) == int(tokens[0])):
                if('=' in line):
                    var_name = line.split('=')[0].strip(';').strip('\t')
                    if(var_name.strip().find(' ')):
                        var_name = var_name.split(' ')[-2].strip('(')
                else:
                    var_name = line.strip('\t').split(' ')
                    if(len(var_name) > 1):
                        var_name = var_name[1].strip('\n').strip(';')
                    else:
                        var_name = var_name[0].strip('\n').strip(';')

        return var_name + " " + tokens[1]

    def approximate_for_all_paths_summary(self, result_path, source_path, ktest_tool_path):
        # create all path objects
        paths = []
        scaling = 1.0
        probability_sum = 0.0
        for root, dirs, files in os.walk(result_path):
            for filename in files:
                if filename.endswith(".prob"):
                    with open(result_path + filename, 'r') as fin:
                        idx = int(fin.readline().split(",")[2].strip())
                        prob = float(fin.readline().split(",")[1])
                        probability_sum += prob
                        new_path = path.Path(idx, prob)
                        paths.append(new_path)

        # Get the input variables and their types and mark those for which error is tracked
        # TODO: Handle floats converted to ints (we only need to do this handling if the conversion happened in the input)
        source = open(source_path, "r")
        input_variables = []
        for line in source:
            if re.match("(.*)klee_make_symbolic(.*)", line):
                tokens = re.split(r'[(|)]|\"', line)
                input_variables.append((tokens[2], tokens[4]))
        source.close()
        # print(input_variables)

        source = open(source_path, "r")
        approximable_input = []
        for line in source:
            if re.match("(.*)klee_track_error(.*)", line):
                tokens = re.split(r'[(|)]|\"|&|,', line)
                approximable_input.append(tokens[2])
        source.close()

        # Maintain a measure of the approximability of the input
        input_approximability_count = []
        expression_count = 0
        for var in approximable_input:
            input_approximability_count.append(0)

        # find approximable variables in each path
        all_variables = set()
        for p in paths:
            # Get the path condition with error
            path_condition_with_error = ""
            source = open(result_path + "test" + "{:0>6}".format(str(p.path_id)) + ".kquery_precision_error", "r")
            for line in source:
                path_condition_with_error += line.rstrip("\n\r")
                path_condition_with_error += " "
            source.close()
            path_condition_with_error = path_condition_with_error.replace("!", "not")
            path_condition_with_error = path_condition_with_error.replace(" = ", " == ")
            path_condition_with_error = path_condition_with_error.replace("&&", "and")
            path_condition_with_error = path_condition_with_error.replace(">> 0", "")
            path_condition_with_error = path_condition_with_error.replace(">> ", "/2**")
            path_condition_with_error = path_condition_with_error.replace("<< ", "*2**")

            # generate an input, for which the path condition is satisfied
            result = subprocess.run([ktest_tool_path, '--write-ints', result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.ktest'], stdout=subprocess.PIPE)
            output_string = result.stdout.decode('utf-8')
            tokens = re.split(r'\n|:', output_string)
            idx = 5
            num_args = int(tokens[idx].strip())
            for args in range(num_args):
                exec("%s = %d" % (tokens[idx + 3].strip().replace("'", ""), int(tokens[idx + 9].strip())))
                idx += 9

            if(not os.path.isfile(result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.precision_error')):
                continue

            with open(result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.precision_error', 'r') as infile:
                for line in infile:
                    method_name_line_tokens = line.split()
                    if(len(method_name_line_tokens) > 0 and method_name_line_tokens[0] == 'Line'):
                        method_name = method_name_line_tokens[4].rstrip(':')

                        # process expression line
                        next_line = infile.readline()
                        tokens = next_line.split()
                        if(len(tokens) > 0 and tokens[0] == 'Output'):
                            expression_count += 1

                            # if the error expression is 0, add to non-approximable list
                            if(tokens[5] == '0'):
                                p.non_approximable_var.append((tokens[3].strip(), method_name))
                                all_variables.add(tokens[3])
                                p.all_var.append(tokens[3].strip())
                                continue

                            # read and sanitize expression
                            exp = next_line.split(' ', 5)[5].strip("\n")
                            exp = exp.replace(">> 0", "")
                            exp = exp.replace(">> ", "/2**")
                            exp = exp.replace("<< ", "*2**")

                            is_var_approximable = 0
                            average_sensitivy = 0.0

                            # For each approximable input variable
                            for idx, var in enumerate(approximable_input):
                                # assign other variable errors to zero
                                for temp_var in approximable_input:
                                    var_with_err_name = temp_var + "_err"
                                    exec("%s = %f" % (var_with_err_name, 0.0))

                                # for repeat
                                result = []
                                input_error_repeat = 100
                                for x in range(input_error_repeat):
                                    # Generate a random error value in (0,1) for the concerned variable
                                    var_with_err_name = var + "_err"
                                    input_error = random.uniform(0.0, 1.0)
                                    exec("%s = %f" % (var_with_err_name, input_error))

                                    # Check if path condition with error is satisfied
                                    if(eval(path_condition_with_error)):
                                        # If satisfied, get the output error from expression
                                        output_error = eval(exp)
                                        result.append((input_error, output_error))
                                        input_approximability_count[idx] += 1

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
                                        if(b_1 <= 0.5):
                                            is_var_approximable = 1

                            # If for at least one variable in the expression, the output is approximable, then add to approximable list.
                            # Else add to the non-approximable list
                            all_variables.add(tokens[3].strip())
                            p.all_var.append(tokens[3].strip())
                            if(is_var_approximable):
                                p.approximable_var.append((tokens[3].strip(), method_name))
                            else:
                                p.non_approximable_var.append((tokens[3].strip(), method_name))
                    else:
                        continue

        approximability_result = []
        for var in all_variables:
            path_score = 0.0
            prob_score = 0.0
            number_of_paths_present_count = 0
            approximable_paths_count = 0
            for p in paths:
                # if variable appears in that path
                if(var in p.all_var):
                    number_of_paths_present_count += 1

                # if in approximable list
                if(len(p.approximable_var) > 0):
                    approximable_var_in_path = list(zip(*p.approximable_var))[0]
                    if(var in approximable_var_in_path):
                        approximable_paths_count += 1
                        prob_score += p.path_prob

            path_score = approximable_paths_count * 100 / number_of_paths_present_count
            prob_score = prob_score * 100 / probability_sum
            approximability_result.append((var, path_score, prob_score))

        print("Source: " + source_path)
        print("Output: " + result_path)
        print("\nApproximability of program variables\n================================")
        print("var_name\tpathscore\tprobability score")
        for result in approximability_result:
            print("%s\t\t%.2f\t\t%e" % (result[0], result[1], result[2]))

        # for p in paths:
        #   print("%d %.2f" %(p.path_id,(p.path_prob * 100 / probability_sum)))

        print("\nApproximability of input variables\n================================")
        for idx, var in enumerate(approximable_input):
            print(var + ' : %d%%' % ((input_approximability_count[idx] / (expression_count * input_error_repeat)) * 100))

    def approximate_for_single_path(self, result_path, source_path, input_path, ktest_tool_path):
        print("Source: " + source_path)
        print("Output: " + result_path + "\n")

        # Find the path longest path with the highest probabilty
        # In case there are more than one, just pick one
        depth = []
        prob = []
        index = []
        exec("scaling = 1.0", None, globals())
        input_error_repeat = 100
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
        if(not path_condition_without_error == ' '):
            path_condition_without_error = path_condition_without_error.replace(" = ", " == ")
            path_condition_without_error = path_condition_without_error.replace(">> 0", "")
            path_condition_without_error = path_condition_without_error.replace(">> ", ">> (int)")
            path_condition_without_error = path_condition_without_error.replace("<< ", "<< (int)")

        #build C function to check satisfiability of path conditions with and without error
        pc_without_error_func = "int without_error() {\n float scaling = 1.0;"
        for var in input_variables:
            if(var[2] == 0):
                pc_without_error_func += "int " + var[1] + ";"
            else:
                pc_without_error_func += "int " + var[1] + "[" + var[3] + "];"

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
                print("%s = %f" % (tokens[idx + 3].strip().replace("'", ""), float(tokens[idx + 9].strip())))
                pc_without_error_func += tokens[idx + 3].strip().replace("'", "") + " = " + str(tokens[idx + 9].strip()) + ";"
            idx += 9

        #load pre-defined input in file (used mainly for floating point constants)
        if(not input_path == ''):
            input_file = open(input_path, "r")
            for line in input_file:
                tokens = line.split('=')
                if('[' in tokens[0] and ']' in tokens[0]):
                    exec("%s.insert(%d, %f)" % (tokens[0].split('[')[0].strip(), int(tokens[0].split('[')[1].split(']')[0].strip()), float(tokens[1])), None, globals())
                    print("%s = %f" % (tokens[0].strip(), float(tokens[1].strip())))
                    pc_without_error_func += tokens[0].strip() + " = " + tokens[1].strip() + ";"
                else:
                    exec("%s = %f" % (tokens[0].strip(), float(tokens[1].strip())), None, globals())
                    print("%s = %f" % (tokens[0].strip(), float(tokens[1].strip())))
                    pc_without_error_func += tokens[0].strip() + " = " + tokens[1].strip() + ";"
            input_file.close()

        pc_with_error_func = pc_without_error_func
        pc_without_error_func += "\nint answer = " + path_condition_without_error + ";\nreturn answer;}"

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
                    exp = exp.replace(">> ", "/2**")
                    exp = exp.replace("<< ", "*2**")

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
                            function_string = pc_with_error_func + error_added_string + "\nint answer = " + path_condition_with_error + ";\nreturn answer;}"

                            # Check if path condition with error is satisfied
                            if(path_condition_with_error == ''):
                                path_with_error_satisfied = 1
                                if(exp == '0'):
                                    non_approximable_var.append((0.0, method_name_line_tokens[2] + ' ' + method_name, 1))
                                    input_approximability_count[idx] += 1
                                    continue
                                else:
                                    output_error = eval(exp, None, globals())
                                    result.append((input_error, output_error))
                                    input_approximability_count[idx] += 1
                            else:
                                func_with_error = cinpy.defc("without_error", ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int), function_string)
                                if(func_with_error(1)):
                                    # If satisfied, get the output error from expression
                                    path_with_error_satisfied = 1
                                    if(exp == '0'):
                                        non_approximable_var.append((0.0, method_name_line_tokens[2] + ' ' + method_name, path_with_error_satisfied))
                                        input_approximability_count[idx] += 1
                                        continue
                                    else:
                                        output_error = eval(exp, None, globals())
                                        result.append((input_error, output_error))
                                        input_approximability_count[idx] += 1

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
                                if(b_1 <= 1):
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
        approximable_var.sort(key=lambda tup: tup[0])
        non_approximable_var.sort(key=lambda tup: tup[0])
        approximable_output_strings = []
        non_approximable_output_strings = []
        for var in approximable_var:
            approximable_output_strings.append(self.get_var_name_from_source(var[1], source_path))
        for var in non_approximable_var:
            if(var[2]):
                non_approximable_output_strings.append(self.get_var_name_from_source(var[1], source_path))
            else:
                non_approximable_output_strings.append(self.get_var_name_from_source(var[1], source_path) + " (Error path not satisifed)")
        #Remove duplicates
        approximable_output_strings = list(set(approximable_output_strings))
        non_approximable_output_strings = list(set(non_approximable_output_strings))

        # Print out the approximable and non-approximable variables
        print("\nApproximable variables(in increasing order of sensitivity)\n================================")
        for var in approximable_input:
            print(var.strip(",") + " (input)")
        for var in approximable_output_strings:
            print(var)

        print("\nNon-approximable variables(in increasing order of sensitivity)\n================================")
        for var in non_approximable_input:
            print(var.strip(",") + " (input)")
        for var in non_approximable_output_strings:
            print(var)

        # Print the approximability of inputs
        print("\nApproximability of input variables\n================================")
        for idx, var in enumerate(approximable_input):
            print(var + ' : %d%%' % ((input_approximability_count[idx] / (expression_count * input_error_repeat)) * 100))


    def approximate_path_by_probability(self, args, result_path, source_path, ktest_tool_path):
        if(not "=" in args):
            print("Usage: python find_approx.py --approximate-path-by-probability=<N>")
            sys.exit()

        probability_threshold = float(args.split('=')[1])
        if(probability_threshold > 100):
            print("Probability threshold should be less than 100")
            sys.exit()

        #print
        print("Source: " + source_path)
        print("Output: " + result_path)
        print("Selected probability threshold: %.2f%%" % probability_threshold)

        # create all path objects
        paths = []
        scaling = 1.0
        probability_sum = 0.0
        for root, dirs, files in os.walk(result_path):
            for filename in files:
                if filename.endswith(".prob"):
                    with open(result_path + filename, 'r') as fin:
                        idx = int(fin.readline().split(",")[2].strip())
                        prob = float(fin.readline().split(",")[1])
                        probability_sum += prob
                        new_path = path.Path(idx, prob)
                        paths.append(new_path)

        # Get the input variables and their types and mark those for which error is tracked
        # TODO: Handle floats converted to ints (we only need to do this handling if the conversion happened in the input)
        source = open(source_path, "r")
        input_variables = []
        for line in source:
            if re.match("(.*)klee_make_symbolic(.*)", line):
                tokens = re.split(r'[(|)]|\"', line)
                input_variables.append((tokens[2], tokens[4]))
        source.close()
        # print(input_variables)

        source = open(source_path, "r")
        approximable_input = []
        for line in source:
            if re.match("(.*)klee_track_error(.*)", line):
                tokens = re.split(r'[(|)]|\"|&|,', line)
                approximable_input.append(tokens[2])
        source.close()

        # Maintain a measure of the approximability of the input
        input_approximability_count = []
        expression_count = 0
        for var in approximable_input:
            input_approximability_count.append(0)

        # Get the non-approximable input
        non_approximable_input = list(set([x[1] for x in input_variables]) - set(approximable_input))

        #sort by path probability
        paths.sort(key=lambda p: p.path_prob)

        # find approximable variables in each path
        running_prob_count = 0.0
        all_variables = set()
        for p in paths:
            running_prob_count += p.path_prob

            if(((running_prob_count * 100) / probability_sum) > probability_threshold):
                break

            # Get the path condition with error
            path_condition_with_error = ""
            source = open(result_path + "test" + "{:0>6}".format(str(p.path_id)) + ".kquery_precision_error", "r")
            for line in source:
                path_condition_with_error += line.rstrip("\n\r")
                path_condition_with_error += " "
            source.close()
            path_condition_with_error = path_condition_with_error.replace("!", "not")
            path_condition_with_error = path_condition_with_error.replace(" = ", " == ")
            path_condition_with_error = path_condition_with_error.replace("&&", "and")
            path_condition_with_error = path_condition_with_error.replace(">> 0", "")
            path_condition_with_error = path_condition_with_error.replace(">> ", "/2**")
            path_condition_with_error = path_condition_with_error.replace("<< ", "*2**")

            # generate an input, for which the path condition is satisfied
            result = subprocess.run([ktest_tool_path, '--write-ints', result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.ktest'], stdout=subprocess.PIPE)
            output_string = result.stdout.decode('utf-8')
            tokens = re.split(r'\n|:', output_string)
            idx = 5
            num_args = int(tokens[idx].strip())
            for args in range(num_args):
                exec("%s = %d" % (tokens[idx + 3].strip().replace("'", ""), int(tokens[idx + 9].strip())))
                idx += 9

            if(not os.path.isfile(result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.precision_error')):
                continue

            with open(result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.precision_error', 'r') as infile:
                for line in infile:
                    method_name_line_tokens = line.split()
                    if(len(method_name_line_tokens) > 0 and method_name_line_tokens[0] == 'Line'):
                        method_name = method_name_line_tokens[4].rstrip(':')

                        # process expression line
                        next_line = infile.readline()
                        tokens = next_line.split()
                        if(len(tokens) > 0 and tokens[0] == 'Output'):
                            expression_count += 1

                            # if the error expression is 0, add to non-approximable list
                            if(tokens[5] == '0'):
                                p.non_approximable_var.append((tokens[3].strip(), method_name))
                                all_variables.add(tokens[3])
                                p.all_var.append(tokens[3].strip())
                                continue

                            # read and sanitize expression
                            exp = next_line.split(' ', 5)[5].strip("\n")
                            exp = exp.replace(">> 0", "")
                            exp = exp.replace(">> ", "/2**")
                            exp = exp.replace("<< ", "*2**")

                            is_var_approximable = 0

                            # For each approximable input variable
                            for idx, var in enumerate(approximable_input):
                                # assign other variable errors to zero
                                for temp_var in approximable_input:
                                    var_with_err_name = temp_var + "_err"
                                    exec("%s = %f" % (var_with_err_name, 0.0))

                                # for repeat
                                result = []
                                input_error_repeat = 100
                                for x in range(input_error_repeat):
                                    # Generate a random error value in (0,1) for the concerned variable
                                    var_with_err_name = var + "_err"
                                    input_error = random.uniform(0.0, 1.0)
                                    exec("%s = %f" % (var_with_err_name, input_error))

                                    # Check if path condition with error is satisfied
                                    if(eval(path_condition_with_error)):
                                        # If satisfied, get the output error from expression
                                        output_error = eval(exp)
                                        result.append((input_error, output_error))
                                        input_approximability_count[idx] += 1

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
                                        if(b_1 <= 0.5):
                                            is_var_approximable = 1

                            # If for at least one variable in the expression, the output is approximable, then add to approximable list.
                            # Else add to the non-approximable list
                            all_variables.add(tokens[3].strip())
                            p.all_var.append(tokens[3].strip())
                            if(is_var_approximable):
                                p.approximable_var.append((tokens[3].strip(), method_name))
                            else:
                                p.non_approximable_var.append((tokens[3].strip(), method_name))
                    else:
                        continue

        approximability_result = []
        for var in all_variables:
            path_score = 0.0
            prob_score = 0.0
            number_of_paths_present_count = 0
            approximable_paths_count = 0
            for p in paths:
                # if variable appears in that path
                if(var in p.all_var):
                    number_of_paths_present_count += 1

                # if in approximable list
                if(len(p.approximable_var) > 0):
                    approximable_var_in_path = list(zip(*p.approximable_var))[0]
                    if(var in approximable_var_in_path):
                        approximable_paths_count += 1
                        prob_score += p.path_prob

            path_score = approximable_paths_count * 100 / number_of_paths_present_count
            prob_score = prob_score * 100 / probability_sum
            approximability_result.append((var, path_score, prob_score))

        print("\nApproximability of program variables\n================================")
        print("var_name\tpathscore\tprobability score")
        for result in approximability_result:
            print("%s\t\t%.2f\t\t%e" % (result[0], result[1], result[2]))

        # for p in paths:
        #   print("%d %.2f" %(p.path_id,(p.path_prob * 100 / probability_sum)))

        print("\nApproximability of input variables\n================================")
        for idx, var in enumerate(approximable_input):
            print(var + ' : %d%%' % ((input_approximability_count[idx] / (expression_count * input_error_repeat)) * 100))


    def approximate_path_by_pathcount(self, args, result_path, source_path, ktest_tool_path):
        if(not "=" in args):
            print("Usage: python find_approx.py --approximate-path-by-pathcount=<N>")
            sys.exit()

        pathcount_threshold = int(args.split('=')[1])
        if(pathcount_threshold > 100):
            print("Path count threshold should be less than 100")
            sys.exit()

        #print
        print("Source: " + source_path)
        print("Output: " + result_path)
        print("Selected path count threshold: %.2f%%" % pathcount_threshold)

        # create all path objects
        paths = []
        scaling = 1.0
        probability_sum = 0.0
        for root, dirs, files in os.walk(result_path):
            for filename in files:
                if filename.endswith(".prob"):
                    with open(result_path + filename, 'r') as fin:
                        idx = int(fin.readline().split(",")[2].strip())
                        prob = float(fin.readline().split(",")[1])
                        new_path = path.Path(idx, prob)
                        paths.append(new_path)
                        probability_sum += prob

        # Get the input variables and their types and mark those for which error is tracked
        # TODO: Handle floats converted to ints (we only need to do this handling if the conversion happened in the input)
        source = open(source_path, "r")
        input_variables = []
        for line in source:
            if re.match("(.*)klee_make_symbolic(.*)", line):
                tokens = re.split(r'[(|)]|\"', line)
                input_variables.append((tokens[2], tokens[4]))
        source.close()
        # print(input_variables)

        source = open(source_path, "r")
        approximable_input = []
        for line in source:
            if re.match("(.*)klee_track_error(.*)", line):
                tokens = re.split(r'[(|)]|\"|&|,', line)
                approximable_input.append(tokens[2])
        source.close()

        # Maintain a measure of the approximability of the input
        input_approximability_count = []
        expression_count = 0
        for var in approximable_input:
            input_approximability_count.append(0)

        # Get the non-approximable input
        non_approximable_input = list(set([x[1] for x in input_variables]) - set(approximable_input))

        #sort by path probability
        paths.sort(key=lambda p: p.path_prob)

        # find approximable variables in each path
        running_path_count = 0.0
        all_variables = set()
        for p in paths:
            running_path_count += 1

            if(((running_path_count * 100) / len(paths)) > pathcount_threshold):
                break

            # Get the path condition with error
            path_condition_with_error = ""
            source = open(result_path + "test" + "{:0>6}".format(str(p.path_id)) + ".kquery_precision_error", "r")
            for line in source:
                path_condition_with_error += line.rstrip("\n\r")
                path_condition_with_error += " "
            source.close()
            path_condition_with_error = path_condition_with_error.replace("!", "not")
            path_condition_with_error = path_condition_with_error.replace(" = ", " == ")
            path_condition_with_error = path_condition_with_error.replace("&&", "and")
            path_condition_with_error = path_condition_with_error.replace(">> 0", "")
            path_condition_with_error = path_condition_with_error.replace(">> ", "/2**")
            path_condition_with_error = path_condition_with_error.replace("<< ", "*2**")

            # generate an input, for which the path condition is satisfied
            result = subprocess.run([ktest_tool_path, '--write-ints', result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.ktest'], stdout=subprocess.PIPE)
            output_string = result.stdout.decode('utf-8')
            tokens = re.split(r'\n|:', output_string)
            idx = 5
            num_args = int(tokens[idx].strip())
            for args in range(num_args):
                exec("%s = %d" % (tokens[idx + 3].strip().replace("'", ""), int(tokens[idx + 9].strip())))
                idx += 9

            if(not os.path.isfile(result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.precision_error')):
                continue

            with open(result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.precision_error', 'r') as infile:
                for line in infile:
                    method_name_line_tokens = line.split()
                    if(len(method_name_line_tokens) > 0 and method_name_line_tokens[0] == 'Line'):
                        method_name = method_name_line_tokens[4].rstrip(':')

                        # process expression line
                        next_line = infile.readline()
                        tokens = next_line.split()
                        if(len(tokens) > 0 and tokens[0] == 'Output'):
                            expression_count += 1

                            # if the error expression is 0, add to non-approximable list
                            if(tokens[5] == '0'):
                                p.non_approximable_var.append((tokens[3].strip(), method_name))
                                all_variables.add(tokens[3])
                                p.all_var.append(tokens[3].strip())
                                continue

                            # read and sanitize expression
                            exp = next_line.split(' ', 5)[5].strip("\n")
                            exp = exp.replace(">> 0", "")
                            exp = exp.replace(">> ", "/2**")
                            exp = exp.replace("<< ", "*2**")

                            is_var_approximable = 0

                            # For each approximable input variable
                            for idx, var in enumerate(approximable_input):
                                # assign other variable errors to zero
                                for temp_var in approximable_input:
                                    var_with_err_name = temp_var + "_err"
                                    exec("%s = %f" % (var_with_err_name, 0.0))

                                # for repeat
                                result = []
                                input_error_repeat = 100
                                for x in range(input_error_repeat):
                                    # Generate a random error value in (0,1) for the concerned variable
                                    var_with_err_name = var + "_err"
                                    input_error = random.uniform(0.0, 1.0)
                                    exec("%s = %f" % (var_with_err_name, input_error))

                                    # Check if path condition with error is satisfied
                                    if(eval(path_condition_with_error)):
                                        # If satisfied, get the output error from expression
                                        output_error = eval(exp)
                                        result.append((input_error, output_error))
                                        input_approximability_count[idx] += 1

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
                                        if(b_1 <= 0.5):
                                            is_var_approximable = 1

                            # If for at least one variable in the expression, the output is approximable, then add to approximable list.
                            # Else add to the non-approximable list
                            all_variables.add(tokens[3].strip())
                            p.all_var.append(tokens[3].strip())
                            if(is_var_approximable):
                                p.approximable_var.append((tokens[3].strip(), method_name))
                            else:
                                p.non_approximable_var.append((tokens[3].strip(), method_name))
                    else:
                        continue

        approximability_result = []
        for var in all_variables:
            path_score = 0.0
            prob_score = 0.0
            number_of_paths_present_count = 0
            approximable_paths_count = 0
            for p in paths:
                # if variable appears in that path
                if(var in p.all_var):
                    number_of_paths_present_count += 1

                # if in approximable list
                if(len(p.approximable_var) > 0):
                    approximable_var_in_path = list(zip(*p.approximable_var))[0]
                    if(var in approximable_var_in_path):
                        approximable_paths_count += 1
                        prob_score += p.path_prob

            path_score = approximable_paths_count * 100 / number_of_paths_present_count
            prob_score = prob_score * 100 / probability_sum
            approximability_result.append((var, path_score, prob_score))

        print("\nApproximability of program variables\n================================")
        print("var_name\tpathscore\tprobability score")
        for result in approximability_result:
            print("%s\t\t%.2f\t\t%e" % (result[0], result[1], result[2]))

        # for p in paths:
        #   print("%d %.2f" %(p.path_id,(p.path_prob * 100 / probability_sum)))

        print("\nApproximability of input variables\n================================")
        for idx, var in enumerate(approximable_input):
            print(var + ' : %d%%' % ((input_approximability_count[idx] / (expression_count * input_error_repeat)) * 100))

    def approximate_for_all_paths(self, result_path, source_path, ktest_tool_path):
        #print
        print("Source: " + source_path)
        print("Output: " + result_path)

        # create all path objects
        paths = []
        scaling = 1.0
        probability_sum = 0.0
        for root, dirs, files in os.walk(result_path):
            for filename in files:
                if filename.endswith(".prob"):
                    with open(result_path + filename, 'r') as fin:
                        idx = int(fin.readline().split(",")[2].strip())
                        prob = float(fin.readline().split(",")[1])
                        probability_sum += prob
                        new_path = path.Path(idx, prob)
                        paths.append(new_path)

        # Get the input variables and their types and mark those for which error is tracked
        # TODO: Handle floats converted to ints (we only need to do this handling if the conversion happened in the input)
        source = open(source_path, "r")
        input_variables = []
        for line in source:
            if re.match("(.*)klee_make_symbolic(.*)", line):
                tokens = re.split(r'[(|)]|\"', line)
                input_variables.append((tokens[2], tokens[4]))
        source.close()
        # print(input_variables)

        source = open(source_path, "r")
        approximable_input = []
        for line in source:
            if re.match("(.*)klee_track_error(.*)", line):
                tokens = re.split(r'[(|)]|\"|&|,', line)
                approximable_input.append(tokens[2])
        source.close()

        # Maintain a measure of the approximability of the input
        input_approximability_count = []
        expression_count = 0
        for var in approximable_input:
            input_approximability_count.append(0)

        # Get the non-approximable input
        non_approximable_input = list(set([x[1] for x in input_variables]) - set(approximable_input))

        paths.sort(key=lambda p: p.path_id)

        # find approximable variables in each path
        all_variables = set()
        for p in paths:
            expression_count = 0
            for var in approximable_input:
                p.input_approximations.append(0)

            # Get the path condition with error
            path_condition_with_error = ""
            source = open(result_path + "test" + "{:0>6}".format(str(p.path_id)) + ".kquery_precision_error", "r")
            for line in source:
                path_condition_with_error += line.rstrip("\n\r")
                path_condition_with_error += " "
            source.close()
            path_condition_with_error = path_condition_with_error.replace("!", "not")
            path_condition_with_error = path_condition_with_error.replace(" = ", " == ")
            path_condition_with_error = path_condition_with_error.replace("&&", "and")
            path_condition_with_error = path_condition_with_error.replace(">> 0", "")
            path_condition_with_error = path_condition_with_error.replace(">> ", "/2**")
            path_condition_with_error = path_condition_with_error.replace("<< ", "*2**")

            # generate an input, for which the path condition is satisfied
            result = subprocess.run([ktest_tool_path, '--write-ints', result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.ktest'], stdout=subprocess.PIPE)
            output_string = result.stdout.decode('utf-8')
            tokens = re.split(r'\n|:', output_string)
            idx = 5
            num_args = int(tokens[idx].strip())
            for args in range(num_args):
                exec("%s = %d" % (tokens[idx + 3].strip().replace("'", ""), int(tokens[idx + 9].strip())))
                idx += 9

            if(not os.path.isfile(result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.precision_error')):
                continue

            with open(result_path + "test" + "{:0>6}".format(str(p.path_id)) + '.precision_error', 'r') as infile:
                for line in infile:
                    method_name_line_tokens = line.split()
                    if(len(method_name_line_tokens) > 0 and method_name_line_tokens[0] == 'Line'):
                        method_name = method_name_line_tokens[4].rstrip(':')

                        # process expression line
                        next_line = infile.readline()
                        tokens = next_line.split()
                        if(len(tokens) > 0 and tokens[0] == 'Output'):
                            expression_count += 1

                            # if the error expression is 0, add to non-approximable list
                            if(tokens[5] == '0'):
                                p.non_approximable_var.append(tokens[3].strip() + ' ' + method_name)
                                all_variables.add(tokens[3])
                                p.all_var.append(tokens[3].strip())
                                continue

                            # read and sanitize expression
                            exp = next_line.split(' ', 5)[5].strip("\n")
                            exp = exp.replace(">> 0", "")
                            exp = exp.replace(">> ", "/2**")
                            exp = exp.replace("<< ", "*2**")

                            is_var_approximable = 0

                            # For each approximable input variable
                            for idx, var in enumerate(approximable_input):
                                # assign other variable errors to zero
                                for temp_var in approximable_input:
                                    var_with_err_name = temp_var + "_err"
                                    exec("%s = %f" % (var_with_err_name, 0.0))

                                # for repeat
                                result = []
                                input_error_repeat = 100
                                for x in range(input_error_repeat):
                                    # Generate a random error value in (0,1) for the concerned variable
                                    var_with_err_name = var + "_err"
                                    input_error = random.uniform(0.0, 1.0)
                                    exec("%s = %f" % (var_with_err_name, input_error))

                                    # Check if path condition with error is satisfied
                                    if(eval(path_condition_with_error)):
                                        # If satisfied, get the output error from expression
                                        output_error = eval(exp)
                                        result.append((input_error, output_error))
                                        input_approximability_count[idx] += 1
                                        p.input_approximations[idx] += 1

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
                                        if(b_1 <= 0.5):
                                            is_var_approximable = 1

                            # If for at least one variable in the expression, the output is approximable, then add to approximable list.
                            # Else add to the non-approximable list
                            all_variables.add(tokens[3].strip())
                            p.all_var.append(tokens[3].strip())
                            if(is_var_approximable):
                                p.approximable_var.append(tokens[3].strip() + ' ' + method_name)
                            else:
                                p.non_approximable_var.append(tokens[3].strip() + ' ' + method_name)
                    else:
                        continue

            print("================================\npath #%d" % p.path_id)
            print("probability: %e" % (p.path_prob * 100 / probability_sum))
            print("\nApproximable variables\n==========")
            for var in approximable_input:
                print(var.strip(",") + " (input)")
            for var in p.approximable_var:
                print(var.strip(","))

            print("\nNon-approximable variables\n==========")
            for var in non_approximable_input:
                print(var.strip(",") + " (input)")

            for var in p.non_approximable_var:
                print(var.strip(","))

            print("\nApproximability of input variables\n==========")
            for idx, var in enumerate(approximable_input):
                print(var + ' : %d%%' % ((input_approximability_count[idx] / (expression_count * input_error_repeat)) * 100))
