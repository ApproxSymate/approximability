import sys
import os

#Run with: python accuracy.py /home/himeshi/Projects/Approx/results/cgo/path-sensitivity/lu_reference.txt /home/himeshi/Projects/workspace/Enerj/lu/klee-out-1/

reference_file = sys.argv[1]
result_path = sys.argv[2]

ref_vars = []

ref_file = open(reference_file, "r")
for line in ref_file:
    tokens = line.split(',')
    ref_vars.append([tokens[0], tokens[1], tokens[2].strip('\n')])

# print(ref_vars)

# Iterate over all paths
paths = []
for root, dirs, files in os.walk(result_path):
    for filename in files:
        if filename.endswith(".prob"):
            with open(result_path + "/" + filename, 'r') as fin:
                paths.append(fin.readline().split(",")[2].strip())

# For each path...
for p in paths:
    selected_path_id = p
    result_file = result_path + "/" + "approximability_" + str(selected_path_id) + ".txt"
    print("Path #" + selected_path_id)
    path_vars = []

    accuracy = 0.0
    tn = 0
    tp = 0

    if "Input values satisfies path condition without error" in open(result_file).read():
        with open(result_file, 'r') as infile:
            for line in infile:
                if(line.startswith("Approximable variables")):
                    line = infile.readline()
                    line = infile.readline()
                    while(line != "\n"):
                        tokens = line.split(' ')
                        path_vars.append([tokens[0].strip('*'), tokens[1].strip('\n').strip(')').strip('('), "Y"])
                        line = infile.readline()

                if(line.startswith("Non-approximable variables")):
                    line = infile.readline()
                    line = infile.readline()
                    while(line != "\n"):
                        tokens = line.split(' ')
                        path_vars.append([tokens[0].strip('*'), tokens[1].strip('\n').strip(')').strip('('), "N"])
                        line = infile.readline()

        for var in ref_vars:
            temp = []
            for result_var in path_vars:
                if(var[0].lower() == result_var[0].lower().strip('+')):
                    if(var[1].lower() in result_var[1].lower() or "input" in result_var[1].lower()):
                        temp.append(result_var)

            if(len(temp) > 1):
                print("More than one entry found in result variables for var:" + var[0])
                print(temp)
                is_approx = "N"
                for item in temp:
                    if(item[2] == "Y"):
                        is_approx = "Y"
                        break
                new_temp = []
                new_temp.append([temp[0][0], temp[0][1], is_approx])
                temp = new_temp

            if(len(temp) == 0):
                print("No entry found in result variables for var:" + var[0] + "," + var[1])
                temp.append([var[0], var[1], "N"])

            if(var[2] == "Y" and temp[0][2] == "Y"):
                tp += 1
            elif(var[2] == "N" and temp[0][2] == "N"):
                tn += 1

        accuracy = ((tn + tp) * 100) / len(ref_vars)

    print("Accuracy: %.2f" % (accuracy))
    print("=================================================")

    # print(path_vars)
