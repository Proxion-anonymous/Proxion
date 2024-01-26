import os





class Parser:

    def remove_comments(self,ls):
        res = []
        inside_comment = False
        for l in ls:
            l = l.strip()
            if inside_comment:
                if '*/' in l:
                    inside_comment = False
                    res.append(l[l.find('*/')+2:])
                else:
                    continue
            elif '/*' in l:
                tmp_line = l
                tmp = ""
                while('/*' in tmp_line):
                    tmp += tmp_line[:tmp_line.find('/*')]
                    tmp_line = tmp_line[tmp_line.find('/*')+2:]
                    if '*/' in tmp_line:
                        tmp_line = tmp_line[tmp_line.find('*/')+2:]
                    else:
                        inside_comment = True
                        break
                if not inside_comment:
                    tmp += tmp_line
                res.append(tmp)
                        
            elif '//' in l:
                tmp = l[:l.find('//')]
                res.append(tmp)
            else:
                res.append(l)
        return res

    #compress each {} in one line
    def compress_to_one_line(self,ls):
        res = []
        index = 0
        tmp = ""
        while(index < len(ls)):
            if len(ls[index]) == 0:
                index += 1
                continue
            if ls[index].strip()[-1] == ';':
                tmp += ls[index]
                res.append(tmp+'\n')
                tmp = ''
                index += 1
            elif '{' in ls[index]:
                cnt = 0
                for c in ls[index]:
                    if c == '{':
                        cnt += 1
                    elif c == '}':
                        cnt -= 1
                        if cnt < 0:
                            print("parse error } more than {")
                            exit()
                tmp += ls[index] + ' '
                index += 1
                while(cnt > 0):
                    for c in ls[index]:
                        if c == '{':
                            cnt += 1
                        elif c == '}':
                            cnt -= 1
                            if cnt < 0:
                                print("parse error } more than {")
                                exit()
                    tmp += ls[index] + ' '
                    index += 1

                res.append(tmp+'\n')
                tmp = ''
                    
            else:
                tmp += ls[index] + ' '
                index += 1
        return res

    # remove import can remove import ... as ...
    def remove_import(self, ls):
        tmp_ls = []
        # get all namespace
        namespaces = set()
        for l in ls:
            if l.startswith("import"):
                if " as " in l:
                    name = l[l.find(' as ')+4:].split(';')[0].strip()
                    namespaces.add(name)
            else:
                tmp_ls.append(l)

        # remove all namespace
        res = []
        for l in tmp_ls:
            for name in namespaces:
                l = l.replace(name+'.', "")

            res.append(l)
                


        return res
            

    def format(self,path, output_path):
        #if file_name != "logic5.sol":
        #    continue
        
        #print(file_name)
        with open(path,"r") as f:
            lines = f.readlines()

        contracts = {}


        # remove comment
        lines = self.remove_comments(lines)
        lines = self.compress_to_one_line(lines)
        lines = self.remove_import(lines)
        #break

                  

        index = 0
        with open(output_path,"w") as f:
            f.write("// SPDX-License-Identifier: BUSL-1.1\n")
            abi_encoder = False  #prevent dup pragma abi
            version = False   # prevent dup pragma solidity
            while index < len(lines):
                if lines[index].startswith("contract") or lines[index].startswith("library") or lines[index].startswith("interface"):
                    contract_name = lines[index].split(' ')[1].strip()
                    contracts[contract_name] = lines[index]
                elif lines[index].startswith("abstract"):
                    contract_name = lines[index].split(' ')[2].strip()
                    contracts[contract_name] = lines[index]
                else:
                    if "ABIEncoder" in lines[index]:
                        if not abi_encoder:
                            abi_encoder = True
                            f.write(lines[index])
                    #elif "SPDX-License-Identifier" in lines[index]:
                    #    if not license:
                    #        license = True
                    #        f.write(lines[index])
                    elif lines[index].startswith("pragma solidity"):
                        if not version:
                            version = True
                            f.write(lines[index])
                    else:
                        f.write(lines[index])
                    
                    #print(lines[index])
                index += 1

            #put contracts in order to make sure inheritance
            writed = set()
            waited = {}
            for c in contracts:
                line = contracts[c]
                declare = line[:line.find('{')]
                if ' is ' in declare:
                    # get all inheritance
                    inherits = declare[declare.find(' is ')+4:].split(',')
                    inherits = [ss.strip() for ss in inherits if len(ss) > 0]
                    waited[c] = inherits
                    #print(inherits)
                else:
                    writed.add(c)
                    f.write(contracts[c])
            while(len(waited) > 0):
                n_waited = {}
                for i in waited:
                    can_write = True
                    for c in waited[i]:
                        if c in waited:
                            can_write = False
                            break
                    if can_write:
                        writed.add(i)
                        f.write(contracts[i])
                    else:
                        n_waited[i] = waited[i]
                waited = n_waited




