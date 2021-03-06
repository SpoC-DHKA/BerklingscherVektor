import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
import keras
from keras.models import Sequential
from keras.layers import Dense, Dropout
from keras.optimizers import SGD
import math
from keras.utils.vis_utils import plot_model
import uuid
from polyaxon_client.tracking import Experiment, get_log_level, get_data_paths, get_outputs_path
from polyaxon_client.tracking.contrib.keras import PolyaxonKeras
import argparse
import os

def readFiles(folder):
    train_x = np.genfromtxt(folder + "/train_x.csv", delimiter='\t', skip_header=True)[:, 1:]
    train_y = np.loadtxt(folder + "/train_y.csv", delimiter='\t', usecols=range(2)[1:], skiprows=1)
    
    test_x = np.genfromtxt(folder + "/test_x.csv", delimiter='\t', skip_header=True)[:, 1:]
    test_y = np.loadtxt(folder + "/test_y.csv", delimiter='\t', usecols=range(2)[1:], skiprows=1)
    
    test_ids = pd.read_csv(folder + "/test_y.csv", delimiter="\t", index_col=0, low_memory=False).index

    eval = np.genfromtxt('/data/shared-task/berkvec_st3/' + cluster +  "/test_y.csv", delimiter='\t', skip_header=True)[:, 1:]
    eval_ids = np.genfromtxt('/data/shared-task/berkvec_st3/' + cluster +  "/test_y.csv", delimiter='\t', skip_header=True)[:, 0:1]

    experiment.log_data_ref(data=train_x, data_name='train_x')
    experiment.log_data_ref(data=train_y, data_name='train_y')
    experiment.log_data_ref(data=test_x, data_name='test_x')
    experiment.log_data_ref(data=test_y, data_name='test_y')
    experiment.log_data_ref(data=eval, data_name='eval')

    return train_x, train_y, test_x, test_y, test_ids, eval, eval_ids

def scaleVectors(train_x, test_x, eval):
    seed = 7
    np.random.seed(seed)
    sc = StandardScaler()
    scaled_train_x = sc.fit_transform(train_x)
    scaled_test_x = sc.transform(test_x)
    scaled_eval = sc.transform(eval)
    return scaled_train_x, scaled_test_x, scaled_eval

def trainClassifier(scaled_train_x, train_y):
    
    # InputSize
    input_dim = len(train_x[0])
    layer_dim = max(input_dim, 64)
    
    # Structure
    classifier = Sequential()
    classifier.add(Dense(layer_dim, activation='relu', input_dim=input_dim))
    classifier.add(Dropout(dropout))
    classifier.add(Dense(layer_dim, activation='relu'))
    classifier.add(Dropout(dropout))
    classifier.add(Dense(1, activation='sigmoid'))
    sgd = SGD(lr=learning_rate, decay=1e-6, momentum=0.9, nesterov=True)
    classifier.compile(loss='binary_crossentropy',
                  optimizer=sgd,
                  metrics=['accuracy'])
    
    metrics = classifier.fit(scaled_train_x, train_y, batch_size = batch_size, epochs = num_epochs, validation_split=0.1, callbacks=[PolyaxonKeras(experiment=experiment)])
    return classifier

def evaluate(true_y, pred_y):
    true_classes = true_y
        
    CR, CA, PFA, GFA, FR, k = 0, 0, 0, 0, 0, 3.0
    for idx, prediction in enumerate(pred_y):
        # the students answer is correct in meaning and language
        # the system says the same -> accept
        if true_classes[idx] == 1 and prediction == 1:
            CA += 1
        # the system says correct meaning wrong language -> reject
        elif true_classes[idx] == 1 and prediction == 0:
            FR += 1

        # students answer is correct in meaning and wrong in language
        #The system says the same -> reject
        elif true_classes[idx] == 0 and prediction == 0:
            CR += 1
        # the system says correct meaning and correct language -> accept
        elif true_classes[idx] == 0 and prediction == 1:
            PFA += 1

    FA = PFA + k * GFA

    experiment.log_metrics(CA=CA)
    experiment.log_metrics(CR=CR)
    experiment.log_metrics(FA=FA)
    experiment.log_metrics(FR=FR)

    Correct = CA + FR
    Incorrect = CR + GFA + PFA
    Df = 0
    if (( CR + FA ) > 0 and CR > 0):
        IncorrectRejectionRate = CR / ( CR + FA + 0.0)
    else:
        IncorrectRejectionRate = 'undefined'

    if (( FR + CA ) > 0 and FR > 0):
        CorrectRejectionRate = FR / ( FR + CA  + 0.0)
    else:
        CorrectRejectionRate = 'undefined'

    if ( CorrectRejectionRate != 'undefined' and IncorrectRejectionRate != 'undefined' and  CorrectRejectionRate != 0) :
        D = IncorrectRejectionRate / CorrectRejectionRate 
        experiment.log_metrics(D=D)
        # Further metrics
        Z = CA + CR + FA + FR
        Ca = CA / Z
        Cr = CR / Z
        Fa = FA / Z
        Fr = FR / Z

        P = Ca / (Ca + Fa + 0.0)
        R = Ca / (Ca + Fr + 0.0)
        SA = Ca + Cr
        F = (2 * P * R)/( P + R + 0.0)
        
        RCa = Ca / (Fr + Ca + 0.0)
        RFa = Fa / (Cr + Fa + 0.0)
        
        print(D)    
        Da = RCa / (RFa + 0.0)

        if ( D != 'undefined' ) :
            Df = math.sqrt((Da*D))
            experiment.log_metrics(Df=Df)
        else:
            Df = 'undefined'
    else:
        D = 'undefined'

    return Df

def testClassifier(classifier, scaled_test_x, test_y, test_ids):
    test_y_pred = classifier.predict_classes(scaled_test_x)
    prediction = dict(zip(test_ids, test_y_pred.flatten()))
    reality = dict(zip(test_ids, test_y))
    return prediction, reality

# Run dat naow
experiment = Experiment()

# 0. Read Args
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    
    parser.add_argument(
        '--cluster',
        default='no cluster given',
        type=str)

    parser.add_argument(
        '--batch_size',
        default=128,
        type=int)

    parser.add_argument(
        '--learning_rate',
        default=0.02,
        type=float)
    
    parser.add_argument(
        '--dropout',
        default=0.2,
        type=float)

    parser.add_argument(
        '--num_epochs',
        default=10,
        type=int)

# Use args for hyperparameter
args = parser.parse_args()
arguments = args.__dict__
cluster = arguments.pop('cluster')

batch_size = None
dropout = None
learning_rate = None
num_epochs = None

if cluster == 'Wo':#90
    batch_size = 128
    dropout = 0.15
    learning_rate = 0.05
    num_epochs = 450
if cluster == 'Wieviel':#81
    batch_size = 64
    dropout = 0.15
    learning_rate = 0.5
    num_epochs = 300
if cluster == 'Welcher':#81
    batch_size = 32
    dropout = 0.12
    learning_rate = 0.07
    num_epochs = 400
if cluster == 'IchWarte':#1
    batch_size = 8
    dropout = 0.1
    learning_rate = 0.12
    num_epochs = 300
if cluster == 'Ichmochte':#87
    batch_size = 128
    dropout = 0.1
    learning_rate = 0.04
    num_epochs = 650
if cluster == 'IchBinHabe':#91
    batch_size = 128
    dropout = 0.1
    learning_rate = 0.02
    num_epochs = 550
if cluster == 'Heisse':#90
    dropout = 0.1
    learning_rate = 0.07
    num_epochs = 200
if cluster == 'GibtEs':#92
    batch_size = 128
    dropout = 0.1
    learning_rate = 0.04
    num_epochs = 600
if cluster == 'FragEinDenWort':#87
    batch_size = 128
    dropout = 0.1
    learning_rate = 0.07
    num_epochs = 400
if cluster == 'AzuB':#92
    batch_size = 128
    dropout = 0.15
    learning_rate = 0.06
    num_epochs = 550
if cluster == 'AprepB':#88
    batch_size = 128
    dropout = 0.1
    learning_rate = 0.03
    num_epochs = 650
if cluster == 'AistB':#87
    batch_size = 128
    dropout = 0.1
    learning_rate = 0.03
    num_epochs = 600
if cluster == 'AinB':#80
    batch_size = 128
    dropout = 0.15
    learning_rate = 0.02
    num_epochs = 600
if cluster == 'AesB':#89
    batch_size = 128
    dropout = 0.1
    learning_rate = 0.05
    num_epochs = 200


fullReality = dict()
fullPrediction = dict()


# Train
train_x, train_y, test_x, test_y, test_ids, eval, eval_ids = readFiles('/data/shared-task/berkvecDH/' + cluster)
scaled_train_x, scaled_test_x, scaled_eval = scaleVectors(train_x, test_x, eval)
classifier = trainClassifier(scaled_train_x, train_y)

# Save
#classifier.save('/data/shared-task/berkvec-models/' + cluster + '.model')

# Test
prediction, reality = testClassifier(classifier, scaled_test_x, test_y, test_ids.values)
fullReality.update(reality)
fullPrediction.update(prediction)

# Eval
eval_y_pred = classifier.predict_classes(scaled_eval)
eval_pred = dict(zip(eval_ids.flatten(), eval_y_pred.flatten()))
print("")
print("{} = {}".format(cluster, eval_pred))
print("")

evaluate(list(fullReality.values()), list(fullPrediction.values()))