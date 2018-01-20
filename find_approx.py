import os
import re
import subprocess
import random
import numpy as np

# Change paths accordingly in config.txt before running
with open('config.txt', 'r') as infile:
    result_path = infile.readline().split()[2].strip()
    source_path = infile.readline().split()[2].strip()
    config_path = infile.readline().split()[2].strip()
    ktest_tool_path = infile.readline().split()[2].strip()

# Find the path longest path with the highest probabilty
# In case there are more than one, just pick one
depth = []
prob = []
index = []
for root, dirs, files in os.walk(result_path):  
    for filename in files:
        if filename.endswith(".prob"):
            with open(result_path + filename, 'r') as fin:
                firstline = fin.readline().split(",")
                index.append(firstline[2].strip())
                secondline = fin.readline().split(",")
                depth.append(secondline[0])
                prob.append(float(secondline[1]))
                
max_depth = max(depth)
max_probabilities = []
max_probabilities_index = []
for idx, val in enumerate(depth):
    if val == max_depth:
        max_probabilities.append(prob[idx])
        max_probabilities_index.append(index[idx])

selected_path_id = max_probabilities_index[max_probabilities.index(max(max_probabilities))]
#print(selected_path_id)

# Get the input variables and their types and mark those for which error is tracked
# TODO: Handle floats converted to ints (we only need to do this handling if the conversion happened in the input)
source = open(source_path, "r")
input_variables = []
for line in source:
    if re.match("(.*)klee_make_symbolic(.*)", line):
        tokens = re.split(r'[(|)]|\"',line)
        input_variables.append((tokens[2],tokens[4]))
source.close()
#print(input_variables)

source = open(source_path, "r")
approximable_input = []
for line in source:
    if re.match("(.*)klee_track_error(.*)", line):
        tokens = re.split(r'[(|)]|\"|&|,',line)
        approximable_input.append(tokens[2])
source.close()
#print(approximable_input)

# Get the path condition with error for the selected path
path_condition = ""
source = open(result_path + "test" + "{:0>6}".format(str(selected_path_id)) + ".kquery_precision_error", "r")
for line in source:
    path_condition += line.rstrip("\n\r")
    path_condition += " "
source.close()
path_condition = path_condition.replace("!", "not")
path_condition = path_condition.replace(" = ", " == ")
path_condition = path_condition.replace("&&", "and")
path_condition = path_condition.replace(">> 0", "")
path_condition = path_condition.replace(">> ", "/2**")
path_condition = path_condition.replace("<< ", "*2**")
#print(path_condition)

#generate an input, for which the path condition is satisfied 
result = subprocess.run([ktest_tool_path, '--write-ints', result_path + "test" + "{:0>6}".format(str(selected_path_id)) + '.ktest'], stdout=subprocess.PIPE)
output_string = result.stdout.decode('utf-8')
tokens = re.split(r'\n|:',output_string)
idx = 5
num_args = int(tokens[idx].strip())
for args in range(num_args):
    exec("%s = %d" % (tokens[idx + 3].strip().replace("'",""), int(tokens[idx + 9].strip())))
    idx += 9
 
#print(output_string)   
#print(tokens[idx + 3].strip().replace("'",""))

approximable_var = []
non_approximable_var = []

# Maintain a measure of the approximability of the input
input_approximability_count = []
for var in approximable_input:
    input_approximability_count.append(0)

# Read expression
with open(result_path + "test" + "{:0>6}".format(str(selected_path_id)) + '.precision_error', 'r') as infile:
    for line in infile:
        method_name_line_tokens = line.split()
        if(len(method_name_line_tokens) > 0 and method_name_line_tokens[0] == 'Line'):
            method_name  = method_name_line_tokens[4].rstrip(':')
        
            next_line = infile.readline()
            tokens = next_line.split()
            if(len(tokens) > 0 and tokens[0] == 'Output'):
                if(tokens[5] == '0'):
                    non_approximable_var.append(tokens[3])
                else:
                    #read and sanitize expression
                    exp = next_line.split(' ', 5)[5].strip("\n")
                    exp = exp.replace(">> 0", "")
                    exp = exp.replace(">> ", "/2**")
                    exp = exp.replace("<< ", "*2**")
                
                    input_error_repeat = 10
                    scaling = 1.0
                    is_var_approximable = 0
                    # For each approximable input variable
                    for idx, var in enumerate(approximable_input):                 
                        #assign other variable errors to zero
                        for temp_var in approximable_input:
                            var_with_err_name = temp_var + "_err"
                            exec("%s = %f" % (var_with_err_name, 0.0))      
                    
                        #for repeat
                        result = []
                        for x in range(input_error_repeat):
                            # Generate a random error value in (0,1) for the concerned variable
                            var_with_err_name = var + "_err"
                            input_error = random.uniform(0.0, 1.0)
                            exec("%s = %f" % (var_with_err_name, input_error))
                        
                            # Check if path condition is satisfied
                            if(eval(path_condition)):
                                # If satisfied, get the output error from expression
                                output_error = eval(exp)
                                result.append((input_error, output_error))

                        if(len(result)):
                            input_approximability_count[idx] += 1
                            # Check for monotonicity of output error. If not monotonous continue to evaluate other inputs.
                            result = sorted(result, key=lambda x: x[0])
                            monotonous_count = 0
                            for index, item in enumerate(result):
                                if(index < (len(result) - 1) and item[1] <= result[index + 1][1]):
                                    monotonous_count += 1
                        
                            # If at least 90% monotonous, get the linear regression gradient
                            if((monotonous_count/(len(result) - 1)) >= 0.8):
                                list_x, list_y = zip(*result)
                            
                                #linear reqression code from https://www.geeksforgeeks.org/linear-regression-python-implementation/
                                xdata = np.array(list_x)
                                ydata = np.array(list_y)
                                n = np.size(xdata)
                                m_x, m_y = np.mean(xdata), np.mean(ydata)
                                SS_xy = np.sum(ydata*xdata - n*m_y*m_x)
                                SS_xx = np.sum(xdata*xdata - n*m_x*m_x)
                                b_1 = SS_xy / SS_xx
                            
                                # If gradient > 50% mark as non-approximable, else continue for other variables in the expression
                                if(b_1 <= 0.5):
                                    is_var_approximable = 1
                                else:
                                    continue
                            else:
                                continue
                        else:
                            continue
            
                    # If for all variables in the expression, the output is approximable, then add to approximable list.
                    # Else add to the non-approximable list
                    if(is_var_approximable):
                        approximable_var.append(tokens[3].strip() + ' ' + method_name)
                    else:
                        non_approximable_var.append(tokens[3].strip() + ' ' + method_name)
        
        else:
            continue
# Get the non-approximable input
non_approximable_input = list(set([x[1] for x in input_variables]) - set(approximable_input))

# Print out the approximable and non-approximable variables
print("Source: " + source_path)
print("Output: " + result_path)
print("\nApproximable variables\n================================")
for var in approximable_input:
    print(var.strip(",") + " (input)")
for var in approximable_var:
    print(var.strip(","))

print("\nNon-approximable variables\n================================")
for var in non_approximable_input:
    print(var.strip(",") + " (input)")
for var in non_approximable_var:
    print(var.strip(","))

# Print the approximability of inputs
print("\nApproximability of input variables\n================================")
for idx, var in enumerate(approximable_input):
    print(var + ' : %d%%' % ((input_approximability_count[idx] / len(approximable_var)) * 100))