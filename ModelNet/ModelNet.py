'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    \file ModelNet.py

    \brief Code to train a classification network on the ModelNet40 dataset.

    \copyright Copyright (c) 2018 Visual Computing group of Ulm University,  
                Germany. See the LICENSE file at the top-level directory of 
                this distribution.

    \author pedro hermosilla (pedro-1.hermosilla-casajus@uni-ulm.de)
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

import sys
import math
import time
import argparse
import importlib
import os
import numpy as np
import tensorflow as tf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.append(os.path.join(ROOT_DIR, 'models'))
sys.path.append(os.path.join(ROOT_DIR, 'utils'))

from utils.PyUtils import visualize_progress
from ModelNetDataSet import ModelNetDataSet

current_milli_time = lambda: time.time() * 1000.0


def create_loss(logits, labels, weigthDecay):
    labels = tf.to_int64(labels)
    cross_entropy = tf.nn.sparse_softmax_cross_entropy_with_logits(labels=labels, logits=logits, name='xentropy')
    xentropyloss = tf.reduce_mean(cross_entropy, name='xentropy_mean')
    regularizer = tf.contrib.layers.l2_regularizer(scale=weigthDecay)
    regVariables = tf.get_collection('weight_decay_loss')
    regTerm = tf.contrib.layers.apply_regularization(regularizer, regVariables)
    return xentropyloss, regTerm


def create_accuracy(logits, labels, scope):
    _, logitsIndexs = tf.nn.top_k(logits)
    with tf.variable_scope(scope):
        return tf.metrics.accuracy(tf.reshape(labels, [-1, 1]), logitsIndexs)


def create_trainning(lossGraph, learningRate, maxLearningRate, learningDecayFactor, learningRateDecay, global_step):
    learningRateExp = tf.train.exponential_decay(learningRate, global_step, learningRateDecay, learningDecayFactor, staircase=True)
    learningRateExp = tf.maximum(learningRateExp, maxLearningRate)
    optimizer = tf.train.AdamOptimizer(learning_rate =learningRateExp)
    update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
    with tf.control_dependencies(update_ops):
        train_op = optimizer.minimize(lossGraph, global_step=global_step)
    return train_op, learningRateExp

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Script to train MCCNN for classification of point clouds (ModelNet40)')
    parser.add_argument('--logFolder', default='log', help='Folder of the output models (default: log)')
    parser.add_argument('--model', default='MCClassS', help='model (default: MCClassS)')
    parser.add_argument('--grow', default=64, type=int, help='Grow rate (default: 64)')
    parser.add_argument('--batchSize', default=32, type=int, help='Batch size  (default: 32)')
    parser.add_argument('--maxEpoch', default=201, type=int, help='Max Epoch  (default: 201)')
    parser.add_argument('--initLearningRate', default=0.005, type=float, help='Init learning rate  (default: 0.005)')
    parser.add_argument('--learningDeacyFactor', default=0.5, type=float, help='Learning deacy factor (default: 0.5)')
    parser.add_argument('--learningDecayRate', default=20, type=int, help='Learning decay rate  (default: 20 Epochs)')
    parser.add_argument('--maxLearningRate', default=0.00001, type=float, help='Maximum Learning rate (default: 0.00001)')
    parser.add_argument('--useDropOut', action='store_true', help='Use drop out  (default: False)')
    parser.add_argument('--dropOutKeepProb', default=0.5, type=float, help='Keep neuron probabillity drop out  (default: 0.5)')
    parser.add_argument('--useDropOutConv', action='store_true', help='Use drop out in convolution layers (default: False)')
    parser.add_argument('--dropOutKeepProbConv', default=0.8, type=float, help='Keep neuron probabillity drop out in convolution layers (default: 0.8)')
    parser.add_argument('--weightDecay', default=0.0, type=float, help='Weight decay (default: 0.0)')
    parser.add_argument('--nPoints', default=1024, type=int, help='Number of points (default: 1024)')
    parser.add_argument('--ptDropOut', default=0.95, type=float, help='Point drop out (default: 0.95)')
    parser.add_argument('--augment', action='store_true', help='Augment data (default: False)')
    parser.add_argument('--nonunif', action='store_true', help='Train on non-uniform (default: False)')
    parser.add_argument('--gpu', default='0', help='GPU (default: 0)')
    parser.add_argument('--gpuMem', default=0.5, type=float, help='GPU memory used (default: 0.5)')
    args = parser.parse_args()

    #Create log folder.
    if not os.path.exists(args.logFolder): os.mkdir(args.logFolder)
    os.system('cp ../models/%s.py %s' % (args.model, args.logFolder))
    os.system('cp ModelNet.py %s' % (args.logFolder))
    logFile = args.logFolder+"/log.txt"

    #Write execution info.
    with open(logFile, "a") as myFile:
        myFile.write("Model: "+args.model+"\n")
        myFile.write("Grow: "+str(args.grow)+"\n")
        myFile.write("BatchSize: "+str(args.batchSize)+"\n")
        myFile.write("MaxEpoch: "+str(args.maxEpoch)+"\n")
        myFile.write("InitLearningRate: "+str(args.initLearningRate)+"\n")
        myFile.write("LearningDeacyFactor: "+str(args.learningDeacyFactor)+"\n")
        myFile.write("LearningDecayRate: "+str(args.learningDecayRate)+"\n")
        myFile.write("MaxLearningRate: "+str(args.maxLearningRate)+"\n")
        myFile.write("UseDropOut: "+str(args.useDropOut)+"\n")
        myFile.write("DropOutKeepProb: "+str(args.dropOutKeepProb)+"\n")
        myFile.write("UseDropOutConv: "+str(args.useDropOutConv)+"\n")
        myFile.write("DropOutKeepProbConv: "+str(args.dropOutKeepProbConv)+"\n")
        myFile.write("WeightDecay: "+str(args.weightDecay)+"\n")
        myFile.write("nPoints: "+str(args.nPoints)+"\n")
        myFile.write("ptDropOut: "+str(args.ptDropOut)+"\n")
        myFile.write("Augment: "+str(args.augment)+"\n")
        myFile.write("Nonunif: "+str(args.nonunif)+"\n")

    print("Model: "+args.model)
    print("Grow: "+str(args.grow))
    print("BatchSize: "+str(args.batchSize))
    print("MaxEpoch: "+str(args.maxEpoch))
    print("InitLearningRate: "+str(args.initLearningRate))
    print("LearningDeacyFactor: "+str(args.learningDeacyFactor))
    print("LearningDecayRate: "+str(args.learningDecayRate))
    print("MaxLearningRate: "+str(args.maxLearningRate))
    print("UseDropOut: "+str(args.useDropOut))
    print("DropOutKeepProb: "+str(args.dropOutKeepProb))
    print("UseDropOutConv: "+str(args.useDropOutConv))
    print("DropOutKeepProbConv: "+str(args.dropOutKeepProbConv))
    print("WeightDecay: "+str(args.weightDecay))
    print("nPoints: "+str(args.nPoints))
    print("ptDropOut: "+str(args.ptDropOut))
    print("Augment: "+str(args.augment))
    print("Nonunif: "+str(args.nonunif))

    #Load the model
    model = importlib.import_module(args.model)

    #Get train and test datasets
    allowedSamplingsTrain=[]
    allowedSamplingsTest=[]
    maxStoredPoints = int(float(args.nPoints)*(2.0-args.ptDropOut))
    if args.nonunif:
        maxStoredPoints = 5000
        allowedSamplingsTrain = [1, 2, 3, 4]
        allowedSamplingsTest = [0, 1, 2, 3, 4]
    else:
        allowedSamplingsTrain = [0]
        allowedSamplingsTest = [0]
    
    mTrainDataSet = ModelNetDataSet(True, args.nPoints, args.ptDropOut, maxStoredPoints, 
        args.batchSize, allowedSamplingsTrain, args.augment)
    mTestDataSet = ModelNetDataSet(False, args.nPoints, 1.0, maxStoredPoints, 
        1, allowedSamplingsTest, False)
    
    numTrainModels = mTrainDataSet.get_num_models()
    numBatchesXEpoch = numTrainModels/args.batchSize
    if numTrainModels%args.batchSize != 0:
        numBatchesXEpoch = numBatchesXEpoch + 1
    numTestModels = mTestDataSet.get_num_models()
    categories = mTrainDataSet.get_categories()
    print(categories)
    print("Train models: " + str(numTrainModels))
    print("Test models: " + str(numTestModels))

    #Create variable and place holders
    global_step = tf.Variable(0, name='global_step', trainable=False)
    inPts = tf.placeholder(tf.float32, [None, 3])
    inBatchIds = tf.placeholder(tf.int32, [None, 1])
    inFeatures = tf.placeholder(tf.float32, [None, 1])
    inLabels = tf.placeholder(tf.int32, [None])
    isTraining = tf.placeholder(tf.bool, shape=())
    keepProbConv = tf.placeholder(tf.float32)
    keepProbFull = tf.placeholder(tf.float32)

    #Create the network
    logits = model.create_network(inPts, inBatchIds, inFeatures, 1, args.batchSize, args.grow, len(categories), 
        isTraining, keepProbConv, keepProbFull, args.useDropOutConv, args.useDropOut)
          
    #Create loss
    xentropyLoss, regularizationLoss = create_loss(logits, inLabels, args.weightDecay)
    loss = xentropyLoss + regularizationLoss

    #Create training
    trainning, learningRateExp = create_trainning(loss, 
        args.initLearningRate, args.maxLearningRate, args.learningDeacyFactor, 
        args.learningDecayRate*numBatchesXEpoch, global_step)
    learningRateSumm = tf.summary.scalar('learninRate', learningRateExp)

    #Create accuracy metric
    accuracyVal, accuracyAccumOp = create_accuracy(logits, inLabels, 'metrics')
    metricsVars = tf.contrib.framework.get_variables('metrics', collection=tf.GraphKeys.LOCAL_VARIABLES)
    resetMetrics = tf.variables_initializer(metricsVars)

    #Create sumaries
    lossSummary = tf.summary.scalar('loss', loss)
    xEntropyLossSummary = tf.summary.scalar('loss_XEntropy', xentropyLoss)
    regularizationLossSummary = tf.summary.scalar('loss_Regularization', regularizationLoss)
    trainingSummary = tf.summary.merge([lossSummary, xEntropyLossSummary, regularizationLossSummary, learningRateSumm])
    metricsSummary = tf.summary.scalar('accuracy', accuracyVal)
    metricsTestSummary = tf.summary.scalar('Tes_Accuracy', accuracyVal)

    #Create init variables 
    init = tf.global_variables_initializer()
    initLocal = tf.local_variables_initializer()

    #create the saver
    saver = tf.train.Saver()
    
    #Create session
    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=args.gpuMem, visible_device_list=args.gpu)
    sess = tf.Session(config=tf.ConfigProto(gpu_options=gpu_options))
    
    #Create the summary writer
    summary_writer = tf.summary.FileWriter(args.logFolder, sess.graph)
    summary_writer.add_graph(sess.graph)
    
    #Init variables
    sess.run(init, {isTraining: True})
    sess.run(initLocal, {isTraining: True})
    step = 0
    epochStep = 0
    np.random.seed(int(time.time()))
    
    #Train
    for epoch in range(args.maxEpoch):
    
        startEpochTime = current_milli_time()
        startTrainTime = current_milli_time()

        epochStep = 0
        lossInfoCounter = 0
        lossAccumValue = 0.0

        sess.run(resetMetrics, {isTraining: True})

        #Iterate over all the train files
        mTrainDataSet.start_iteration()
        while mTrainDataSet.has_more_batches():
    
            _, points, batchIds, features, _, labels, _ = mTrainDataSet.get_next_batch()
            
            _, lossRes, xentropyLossRes, regularizationLossRes, trainingSummRes, _ = \
                sess.run([trainning, loss, xentropyLoss, regularizationLoss, trainingSummary, accuracyAccumOp], 
                {inPts: points, inBatchIds: batchIds, inFeatures: features, inLabels: labels, isTraining: True, 
                keepProbConv: args.dropOutKeepProbConv, keepProbFull: args.dropOutKeepProb})
            
            summary_writer.add_summary(trainingSummRes, step)

            lossAccumValue += lossRes
            lossInfoCounter += 1

            if lossInfoCounter == 10:
                endTrainTime = current_milli_time()                   
                currAccuracy, metricsSummRes = sess.run([accuracyVal, metricsSummary], {isTraining: False})
                summary_writer.add_summary(metricsSummRes, step)

                visualize_progress(epochStep, numBatchesXEpoch, "Loss: %.6f | Accuracy: %.4f | Time: %.4f" % (
                    lossAccumValue/10.0, currAccuracy*100.0, (endTrainTime-startTrainTime)/1000.0))

                with open(logFile, "a") as myfile:
                    myfile.write("Step: %6d (%4d) | Loss: %.6f | Accuracy: %.4f\n" % (step, epochStep, lossAccumValue/10.0, currAccuracy*100.0))

                sess.run(resetMetrics, {isTraining: True})
                lossInfoCounter = 0
                lossAccumValue = 0.0
                startTrainTime = current_milli_time()

            step += 1
            epochStep += 1

        endEpochTime = current_milli_time()   
        print("Epoch %3d  train time: %.4f" %(epoch, (endEpochTime-startEpochTime)/1000.0))
        with open(logFile, "a") as myfile:
            myfile.write("Epoch %3d  train time: %.4f \n" %(epoch, (endEpochTime-startEpochTime)/1000.0))

        if epoch%10==0:
            saver.save(sess, args.logFolder+"/model.ckpt")

        #Test data
        accumTestLoss = 0.0
        it = 0
        sess.run(resetMetrics, {isTraining: False})
        mTestDataSet.start_iteration()
        while mTestDataSet.has_more_batches():
            _, points, batchIds, features, _, labels, _ = mTestDataSet.get_next_batch()
   
            lossRes, _ = sess.run([loss, accuracyAccumOp], 
                {inPts: points, inBatchIds: batchIds, inFeatures: features, inLabels: labels, isTraining: False, keepProbConv: 1.0, keepProbFull: 1.0})

            accumTestLoss = accumTestLoss + lossRes
            
            if it%100 == 0:
                visualize_progress(it, numTestModels)
            
            it += 1

        totalAccuracy, metricsTestSummRes = sess.run([accuracyVal, metricsTestSummary], {isTraining: False})
        accumTestLoss = accumTestLoss/float(numTestModels)
        summary_writer.add_summary(metricsTestSummRes, step)

        print("Loss: %.6f | Test accuracy: %.4f" % (accumTestLoss, totalAccuracy*100.0))
        with open(logFile, "a") as myfile:
            myfile.write("Loss: %.6f | Test accuracy: %.4f \n" % (accumTestLoss, totalAccuracy*100.0))
