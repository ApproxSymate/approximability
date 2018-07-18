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
            if('=' in line):
                var_name = line.split('=')[0].strip(';').strip('\t')
                if(var_name.strip().find(' ')):
                    var_name = var_name.split(' ')[-2].strip('(')
            elif('klee_bound_error' in line):
                var_name = line.split(',')[1].lstrip().replace('"', '')
            else:
                var_name = line.strip('\t').split(' ')
                if(len(var_name) > 1):
                    var_name = var_name[1].strip('\n').strip(';')
                else:
                    var_name = var_name[0].strip('\n').strip(';')
    # print(var_name + " " + tokens[1])

    return var_name + " " + tokens[1]
