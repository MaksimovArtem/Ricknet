"""An example of how to use your own dataset to train a classifier that recognizes people.
"""
# MIT License
# 
# Copyright (c) 2016 David Sandberg
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
import numpy as np
import argparse
import facenet
import os
import sys
import math
import pickle
import sklearn.metrics
import matplotlib.pyplot as plt
from sklearn.svm import SVC
from sklearn.utils.multiclass import unique_labels
from sklearn.metrics import roc_curve, auc
def main(args):
  
	with tf.Graph().as_default():
	  
		with tf.Session() as sess:
			
			np.random.seed(seed=args.seed)
			
			if args.use_split_dataset:
				dataset_tmp = facenet.get_dataset(args.data_dir)
				train_set, test_set = split_dataset(dataset_tmp, args.min_nrof_images_per_class, args.nrof_train_images_per_class)
				if (args.mode=='TRAIN'):
					dataset = train_set
				elif (args.mode=='CLASSIFY'):
					dataset = test_set
			else:
				dataset = facenet.get_dataset(args.data_dir)

			# Check that there are at least one training image per class
			for cls in dataset:
				assert(len(cls.image_paths)>0, 'There must be at least one image for each class in the dataset')            

				 
			paths, labels = facenet.get_image_paths_and_labels(dataset)
			
			print('Number of classes: %d' % len(dataset))
			print('Number of images: %d' % len(paths))
			
			# Load the model
			print('Loading feature extraction model')
			facenet.load_model(args.model)
			
			# Get input and output tensors
			images_placeholder = tf.get_default_graph().get_tensor_by_name("input:0")
			embeddings = tf.get_default_graph().get_tensor_by_name("embeddings:0")
			phase_train_placeholder = tf.get_default_graph().get_tensor_by_name("phase_train:0")
			embedding_size = embeddings.get_shape()[1]
			
			# Run forward pass to calculate embeddings
			print('Calculating features for images')
			nrof_images = len(paths)
			nrof_batches_per_epoch = int(math.ceil(1.0*nrof_images / args.batch_size))
			emb_array = np.zeros((nrof_images, embedding_size))
			for i in range(nrof_batches_per_epoch):
				start_index = i*args.batch_size
				end_index = min((i+1)*args.batch_size, nrof_images)
				paths_batch = paths[start_index:end_index]
				images = facenet.load_data(paths_batch, False, False, args.image_size)
				feed_dict = { images_placeholder:images, phase_train_placeholder:False }
				emb_array[start_index:end_index,:] = sess.run(embeddings, feed_dict=feed_dict)
			
			classifier_filename_exp = os.path.expanduser(args.classifier_filename)
			y_score = 0

			if (args.mode=='TRAIN'):
				# Train classifier
				print('Training classifier')
				model = SVC(kernel='linear', probability=True, decision_function_shape='ovr')
				y_score = model.fit(emb_array, labels).decision_function(emb_array)

				# Create a list of class names
				class_names = [ cls.name.replace('_', ' ') for cls in dataset]

				#print(y_test)

				# Saving classifier model
				with open(classifier_filename_exp, 'wb') as outfile:
					pickle.dump((model, class_names), outfile)
				print('Saved classifier model to file "%s"' % classifier_filename_exp)

			elif (args.mode=='CLASSIFY'):
				# Classify images
				print('Testing classifier')
				with open(classifier_filename_exp, 'rb') as infile:
					(model, class_names) = pickle.load(infile)

				print('Loaded classifier model from file "%s"' % classifier_filename_exp)

				predictions = model.predict_proba(emb_array)
				best_class_indices = np.argmax(predictions, axis=1)
				best_class_probabilities = predictions[np.arange(len(best_class_indices)), best_class_indices]
				
				success = 0

				labels2 = []
				for i in range(len(labels)):
					if labels[i] == 1:
						labels2.append("risky")
					else:
						labels2.append("non risky")

				for i in range(len(best_class_indices)):
					string1 = paths[i]

					if class_names[best_class_indices[i]] == labels2[i]:
						success += 1
					print('%4d  %s  true_label - %s: %.3f' % (i, class_names[best_class_indices[i]], labels[i], best_class_probabilities[i]))

				accuracy = np.mean(np.equal(best_class_indices, labels))
				print('Accuracy: %.3f' % accuracy)
				print('Images in test: {}'.format(len(best_class_indices)))
				print('Success {}'.format(success))

				#Confusion_matrix plotting
				class_names=np.array(['non risky', 'risky'], dtype='<U10')
				np.set_printoptions(precision=2)
				plot_confusion_matrix(labels, best_class_indices, classes=class_names,
                          normalize=True,
                          title=None,
                          cmap=plt.cm.Blues)
				
				plt.savefig('matrix.jpeg')
				
				#ROC calculating
				y_test = [np.ndarray(shape=(1,2), buffer=np.array([1,0]), dtype=int) for i in range(9)] + [np.ndarray(shape=(1,2), buffer=np.array([0,1]), dtype=int) for i in range (9)]
				y_test = np.ndarray(shape=(18,2), buffer = np.array(y_test),dtype=int)

				fpr = dict()
				tpr = dict()
				roc_auc = dict()

				score = model.predict(emb_array).ravel()
				for i in range(2):
					fpr[i], tpr[i], _ = roc_curve(y_test[:,i], score)
					roc_auc[i] = auc(fpr[i], tpr[i])
				
				# Compute micro-average ROC curve and ROC area
				fpr["micro"], tpr["micro"], _ = roc_curve(y_test.ravel(), predictions.ravel())
				roc_auc["micro"] = auc(fpr["micro"], tpr["micro"])

				#ROC plotting
				plt.figure()
				lw = 1
				plt.plot(fpr[1], tpr[1], color='darkorange',
		 			lw=lw, label='ROC curve (area = %0.2f)' % roc_auc[1])
				plt.plot([0, 1], [0, 1], color='navy', lw=lw, linestyle='--')
				plt.xlim([0.0, 1.0])
				plt.ylim([0.0, 1.05])
				plt.xlabel('False Positive Rate')
				plt.ylabel('True Positive Rate')
				plt.title('Receiver operating characteristic example')
				plt.legend(loc="lower right")
				plt.savefig('roc.jpeg')
			
def split_dataset(dataset, min_nrof_images_per_class, nrof_train_images_per_class):
	train_set = []
	test_set = []
	for cls in dataset:
		paths = cls.image_paths
		# Remove classes with less than min_nrof_images_per_class
		if len(paths)>=min_nrof_images_per_class:
			np.random.shuffle(paths)
			train_set.append(facenet.ImageClass(cls.name, paths[:nrof_train_images_per_class]))
			test_set.append(facenet.ImageClass(cls.name, paths[nrof_train_images_per_class:]))
	return train_set, test_set

			
def parse_arguments(argv):
	parser = argparse.ArgumentParser()
	
	parser.add_argument('mode', type=str, choices=['TRAIN', 'CLASSIFY'],
		help='Indicates if a new classifier should be trained or a classification ' + 
		'model should be used for classification', default='CLASSIFY')
	parser.add_argument('data_dir', type=str,
		help='Path to the data directory containing aligned LFW face patches.')
	parser.add_argument('model', type=str, 
		help='Could be either a directory containing the meta_file and ckpt_file or a model protobuf (.pb) file')
	parser.add_argument('classifier_filename', 
		help='Classifier model file name as a pickle (.pkl) file. ' + 
		'For training this is the output and for classification this is an input.')
	parser.add_argument('--use_split_dataset', 
		help='Indicates that the dataset specified by data_dir should be split into a training and test set. ' +  
		'Otherwise a separate test set can be specified using the test_data_dir option.', action='store_true')
	parser.add_argument('--test_data_dir', type=str,
		help='Path to the test data directory containing aligned images used for testing.')
	parser.add_argument('--batch_size', type=int,
		help='Number of images to process in a batch.', default=90)
	parser.add_argument('--image_size', type=int,
		help='Image size (height, width) in pixels.', default=160)
	parser.add_argument('--seed', type=int,
		help='Random seed.', default=666)
	parser.add_argument('--min_nrof_images_per_class', type=int,
		help='Only include classes with at least this number of images in the dataset', default=20)
	parser.add_argument('--nrof_train_images_per_class', type=int,
		help='Use this number of images from each class for training and the rest for testing', default=10)
	
	return parser.parse_args(argv)


def plot_confusion_matrix(y_true, y_pred, classes,
                          normalize=False,
                          title=None,
                          cmap=plt.cm.Blues):
    """
    This function prints and plots the confusion matrix.
    Normalization can be applied by setting `normalize=True`.
    """
    if not title:
        if normalize:
            title = 'Normalized confusion matrix'
        else:
            title = 'Confusion matrix, without normalization'

    # Compute confusion matrix
    cm = sklearn.metrics.confusion_matrix(y_true, y_pred)
    # Only use the labels that appear in the data
    classes = classes[unique_labels(y_true, y_pred)]
    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        #print("Normalized confusion matrix")
    #else:
        #print('Confusion matrix, without normalization')

    #print(cm)

    fig, ax = plt.subplots()
    im = ax.imshow(cm, interpolation='nearest', cmap=cmap)
    ax.figure.colorbar(im, ax=ax)
    # We want to show all ticks...
    ax.set(xticks=np.arange(cm.shape[1]),
           yticks=np.arange(cm.shape[0]),
           # ... and label them with the respective list entries
           xticklabels=classes, yticklabels=classes,
           title=title,
           ylabel='True label',
           xlabel='Predicted label')

    # Rotate the tick labels and set their alignment.
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right",
             rotation_mode="anchor")

    # Loop over data dimensions and create text annotations.
    fmt = '.2f' if normalize else 'd'
    thresh = cm.max() / 2.
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, format(cm[i, j], fmt),
                    ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black")
    fig.tight_layout()
    return ax

if __name__ == '__main__':
	main(parse_arguments(sys.argv[1:]))

