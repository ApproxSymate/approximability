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
