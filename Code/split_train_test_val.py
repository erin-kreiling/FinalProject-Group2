#import numpy as np
import os
#sotu = open('SOTU.txt', 'r')
#np.save('SOTU.npy', sotu, allow_pickle=True)
#wordsList = np.load('SOTU.npy')
#wordsList = wordsList.tolist()
#wordsList = [word.decode('UTF-8') for word in wordsList]
#print(wordsList.ndim)

def get_file_list_from_dir(datadir):
    all_files = os.listdir(os.path.abspath(datadir))
    data_files = list(filter(lambda file: file.endswith('.txt'), all_files))
    return data_files

file_list = get_file_list_from_dir('/home/ubuntu/erinkreiling_finalproject/Data')
#print(file_list)

import random
random.shuffle(file_list)
#print file_list

from math import floor

def get_training_and_testing_sets(file_list):
    split = 0.7
    split_index = floor(len(file_list) * split)
    split_index = int(split_index)
    training = file_list[:split_index]
    testing = file_list[split_index:]
    return training, testing

training = get_training_and_testing_sets(file_list)[0]
testing = get_training_and_testing_sets(file_list)[1]
validation = testing[0:35]
testing = testing[35:]


with open('sotu.train.txt', 'w') as outfile:
    for fname in training:
        with open(fname) as infile:
            for line in infile:
                outfile.write(line)

with open('sotu.test.txt', 'w') as outfile:
    for fname in testing:
        with open(fname) as infile:
            for line in infile:
                outfile.write(line)

with open('sotu.valid.txt', 'w') as outfile:
    for fname in validation:
        with open(fname) as infile:
            for line in infile:
                outfile.write(line)



print(len())