import re
import os
import subprocess
import random
import numpy as np
import path
import sys
import ctypes
import cinpy

def approximate_path_by_pathcount(args, result_path, source_path, ktest_tool_path):
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
    input_error_repeat = 100
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
        