from keras.models import load_model
from collections import OrderedDict
from keras.layers import Embedding, Dense, Input, merge, SimpleRNN, GRU, LSTM, Masking
from keras.layers.wrappers import TimeDistributed
import keras.preprocessing.sequence
import os
from .callbacks import TrainingHistory, VisualiseEmbeddings
from ..arithmetics import MathTreebank
from GRU_output_gates import GRU_output_gates
from keras.models import ArithmeticModel
import theano
import copy
import matplotlib
# matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import random


class Training(object):
    # TODO write which functions a training class should implement
    """
    Give elaborate description
    functions that need to be implemented:
        - _build
        - init (set lossfunction and metrics)
        - train
    """
    def __init__(self, digits=np.arange(-10,11), operators=['+', '-']):
        """
        Create training architecture
        """
        # set dmap
        self.dmap = self._dmap(digits, operators)
        self.input_dim = len(self.dmap)+1
        self.digits = digits
        self.operators = operators
        self.activation_func = None
        self.gate_activation_func = None

    def generate_model(self, recurrent_layer, input_size, input_length, size_hidden,
                       W_embeddings=None, W_recurrent=None, W_classifier=None,
                       fix_classifier_weights=False, fix_embeddings=False, 
                       fix_recurrent_weights=False, mask_zero=True,
                       dropout_recurrent=0.0, **kwargs):
        """
        Generate the model to be trained
        :param recurrent_layer:     type of recurrent layer (from keras.layers SimpleRNN, GRU or LSTM)
        :param input_size:          dimensionality of the embeddings (input size recurrent layer)
        :param input_length:        max sequence length
        :param size_hidden:         size recurrent layer
        :param W_embeddings:        Either an embeddings matrix or None if to be generated by keras layer
        :param W_recurrent:         Either weights for the recurrent matrix or None if to be generated by keras layer
        :param W_classifier:        Either weights for the classifier or None if to be generated by keras layer
        :param train_embeddings:    set to false to fix embedding weights during training
        :param train_classifier:    set to false to fix classifier layer weights during training
        :param train_recurrent:     set to false to fix recurrent weights during training
        :param mask_zero:           set to true to mask 0 values
        :param dropout_recurrent:   dropout param for recurrent weights
        :return:
        """

        # set network attributes
        self.recurrent_layer = recurrent_layer
        self.input_size = input_size
        self.input_length = input_length
        self.size_hidden = size_hidden
        self.train_classifier = not fix_classifier_weights
        self.train_embeddings = not fix_embeddings
        self.train_recurrent = not fix_recurrent_weights
        self.mask_zero = mask_zero
        self.dropout_recurrent = dropout_recurrent
        self.trainings_history = None
        self.model = None
        if 'classifiers' in kwargs:
            self.classifiers = kwargs['classifiers']

        # build model
        self._build(W_embeddings, W_recurrent, W_classifier)


    def add_pretrained_model(self, model, copy_weights=['recurrent','embeddings','classifier'], fix_classifier_weights=False, fix_embeddings=False, fix_recurrent_weights=False, mask_zero=True, dropout_recurrent=0.0, **kwargs):
        """
        Add a model with already trained weights. Model can be originally
        from a different training architecture, check which weights should be
        copied.
        :param model:           A keras model
        :param model_weights:   h5 file containing model weights
        :param copy_weights:    determines which weights should be copied
        """

        if isinstance(model, str):
            model = load_model(model)

        model_info = self.get_model_info(model)

        if model_info['input_dim'] != self.input_dim:
            raise ValueError("dmap mismatch: input dimensionality of pretrained model does not match the expected inputs")

        if model_info['dmap'] != self.dmap:
            raise ValueError("Model dmap is not identical to architecture dmap")

        # find recurrent layer
        recurrent_layer = {'SimpleRNN': SimpleRNN, 'GRU': GRU, 'LSTM': LSTM}[model_info['recurrent_layer']]

        W_recurrent, W_embeddings, W_classifier = None, None, None

        # override weights with model weights
        if 'recurrent' in copy_weights:
            W_recurrent = model_info['weights_recurrent']

        if 'embeddings' in copy_weights:
            W_embeddings = model_info['weights_embeddings']

        if 'classifier' in copy_weights:
            W_classifier = model_info['classifiers']


        input_length = kwargs.get('input_length', model_info['input_length'])
        kwargs.pop('input_length', None)

        # run build function
        self.generate_model(recurrent_layer=recurrent_layer, input_size=model_info['input_size'], input_length=input_length, size_hidden=model_info['size_hidden'], W_embeddings=W_embeddings, W_recurrent=W_recurrent, W_classifier=W_classifier, fix_classifier_weights=fix_classifier_weights, fix_embeddings=fix_embeddings, fix_recurrent_weights=fix_recurrent_weights, **kwargs)
        return

    @staticmethod
    def _dmap(digits, operators):
        """
        Generate a map from integers to digits
        and operators. Be very careful changing this map,
        using different dmaps across training and testing
        will not give sensible results.
        """
        N_operators = len(operators)
        N_digits = len(digits)
        N = N_digits + N_operators + 2
        digits_str = [str(i) for i in digits]
        # start counting at 1 to not ignore first word during training
        dmap = OrderedDict(zip(digits_str+operators+['(', ')'], np.arange(1, N+1)))

        return dmap

    def generate_training_data(self, data, digits=np.arange(-10, 11), format='infix', pad_to=None):
        """
        Generate training data
        """
        # check if digits are in dmap of model
        assert not bool(set(digits) - set(self.digits)), "Model cannot process inputted digits"

        if isinstance(data, dict):
            data = MathTreebank(data, digits=digits)
            random.shuffle(data.examples)

        return self.data_from_treebank(treebank=data,
                                       format=format,
                                       pad_to=pad_to)


    def _build(self, W_embeddings, W_recurrent, W_classifier):
        raise NotImplementedError("Should be implemented in subclass")

    def generate_test_data(self, data, digits, test_separately=True, format='infix', pad_to=None):
        """
        Take a dictionary that maps language names to number of sentences for 
        which to create test data. Return dictionary with classifier name 
        as key and test data as output.
        :param languages:       can be either:
                                    - a dictionary mapping language names to numbers
                                    - a list with (name, treebank) tuples
                                    - a MathTreebank object
        :return:                dictionary mapping classifier names to targets
        UNTESTED
        """

        if isinstance(data, list):
            test_data = []
            for name, treebank in data:
                X_test, Y_test = self.data_from_treebank(treebank, format=format, pad_to=pad_to)
                test_data.append((name, X_test, Y_test))

        elif isinstance(data, MathTreebank):
            X_test, Y_test = self.data_from_treebank(data, format=format, pad_to=None)
            test_data = [('test treebank', X_test, Y_test)]

        elif test_separately:
            test_data = []
            for name, N in data.items():
                X, Y = self.generate_training_data(data={name: N}, digits=digits, format=format, pad_to=pad_to)
                test_data.append((name, X, Y))

        else:
            X, Y = self.generate_training_data(data=data, digits=digits, format=format, pad_to=pad_to)
            name = ', '.join(data.keys())
            test_data = [(name, X, Y)]

        return test_data

    def train(self, training_data, batch_size, epochs, filename, optimizer='adam', metrics=None, loss_function=None, validation_split=0.1, validation_data=None, sample_weight=None, verbosity=2, visualise_embeddings=False, logger=False, save_every=False):
        """
        Fit the model.
        :param weights_animation:    Set to true to create an animation of the development of the embeddings
                                        after training.
        :param visualise_embeddings:        Set to N to plot the embeddings every N epochs, only available for 2D
                                        embeddings.
        """
        X_train, Y_train = training_data

        if not metrics:
            metrics = self.metrics
        if not loss_function:
            loss_function = self.loss_function

        # compile model
        self.model.compile(loss=loss_function, optimizer=optimizer, metrics=metrics)

        callbacks = self.generate_callbacks(visualise_embeddings, logger, recurrent_id=self.get_recurrent_layer_id(), embeddings_id=self.get_embeddings_layer_id(), save_every=save_every, filename=filename)

        sample_weight = self.get_sample_weights(training_data, sample_weight)

        # fit model
        self.model.fit(X_train, Y_train, validation_data=validation_data,
                       validation_split=validation_split, batch_size=batch_size, 
                       nb_epoch=epochs, sample_weight=sample_weight,
                       callbacks=callbacks, verbose=verbosity, shuffle=True)

        hist = callbacks[0]

        self.trainings_history = hist                    # set trainings history as attribute

    def print_accuracies(self, history=None):
        """
        Print accuracies for training en test sets in readable fashion.
        UNTESTED
        """
        if history:
            hist = history

        elif not self.trainings_history:
            print("Model not trained yet")
            return

        else:
            hist = self.trainings_history

        print "Accuracy for for training set %s:\t" % \
              '\t'.join(['%s: %f' % (item[0], item[1][-1]) for item in hist.metrics_train.items()])
        print "Accuracy for for validation set %s:\t" % \
              '\t'.join(['%s: %f' % (item[0], item[1][-1]) for item in hist.metrics_val.items()])

    def test(self, test_data, metrics=None):
        """
        Test model and print results. Return a dictionary with the results.
        """
        # input new metrics
        if metrics:
            self.model.compile(loss=self.loss_function, optimizer='adam', metrics=metrics)

        else:
            self.model.compile(loss=self.loss_function, optimizer='adam', metrics=self.metrics)

        evaluation = OrderedDict()
        for name, X, Y in test_data:
            acc = self.model.evaluate(X, Y)
            evaluation[name] = dict([(self.model.metrics_names[i], acc[i]) for i in xrange(len(acc))])
        return evaluation

    def get_activations(self, input_data):
        """
        Get the activation values of the hidden layer
        given an input.
        """
        if not self.activation_func:
            self._make_activation_func()

        return self.activations_func(input_data)[0]

    def get_gate_activations(self, input_data):
        """
        Get the gate activations of the hidden
        layer given an array with input data.
        """
        if not self.gate_activation_func:
            self._make_gate_activation_func()

        all_activations = self.gate_activation_func(input_data)[0]

        hl_activations = all_activations[:,:,:self.rec_dim]
        z = all_activations[:,:,self.rec_dim:2*self.rec_dim]
        r = all_activations[:,:,2*self.rec_dim:]
        return hl_activations, z, r

    def _make_activation_func(self):

        self.activations_func = theano.function([self.model.layers[0].input], [self.model.layers[self.get_recurrent_layer_id()].output])

    def _make_gate_activation_func(self):

        rec_id = self.get_recurrent_layer_id()

        recurrent_layer = self.model.layers[rec_id]

        assert recurrent_layer.__class__.__name__ == 'GRU', "get gate activations only implemented for GRU"

        # get config of recurrent layer, set config
        rec_config = recurrent_layer.get_config()
        self.rec_dim = rec_config['output_dim']

        gate_output_layer = GRU_output_gates(output_dim=rec_config['output_dim'],
                                             input_length=rec_config['input_length'],
                                             activation=rec_config['activation'],
                                             weights=recurrent_layer.get_weights(),
                                             return_sequences=True)(
                                                     self.model.layers[rec_id-1].get_output_at(0))

        self.gate_activation_func = theano.function([self.model.layers[0].input], [gate_output_layer])








    def evaluation_string(self, evaluation):
        """
        Print evaluation results in a readable fashion.
        """
        eval_str = ''
        for name in evaluation:
            eval_str += "\n%s:" % name
            eval_str += '\t'.join(['%s: %f' % (metric, value) for metric, value in evaluation[name].items()])

        return eval_str

    def get_sample_weights(self, training_data, sample_weight):
        """
        Return a matrix with sample weights for the 
        input data if sample_weight parameter is true.
        """
        if not sample_weight:
            return None

        X_dict, Y_dict = training_data

        if len(X_dict) != 1:
            raise NotImplementedError("Number of inputs larger than 1, didn't think I'd need this case so I didn't implement it")

        sample_weights = {}
        for output in Y_dict:
            dim = Y_dict[output].ndim
            if dim == 2:
                # use sample_weight only for seq2seq models
                return None
            else:
                X_padded = X_dict.values()[0]
                sample_weight = np.zeros_like(X_padded)
                sample_weight[X_padded != 0] = 1
                sample_weights[output] = sample_weight

        return sample_weights

    def model_summary(self):
        print(self.model.summary())

    @staticmethod
    def get_model_info(model):
        """
        Get different type of weights from a json model. Check
        if network falls in family of networks that we are
        studying in this project: one layer recurrent neural
        networks that are trained with one of the architectures
        in from the Training type.
        """

        # check if model is of correct type TODO
        n_layers = len(model.layers)

        # create list with layer objects

        model_info = {}
        model_info['classifiers'] = {}
        model_info['dmap'] = model.dmap
        # loop through layers to get weight matrices

        for n_layer in xrange(n_layers):
            layer = model.layers[n_layer]
            layer_type = model.get_config()['layers'][n_layer]['class_name']
            weights = layer.get_weights()

            if layer_type == 'InputLayer':
                # decide on architecture by checking # of input layers
                if 'architecture' in model_info:
                    model_info['architecture'] = 'ComparisonTraining'
                else:
                    model_info['architecture'] = 'ScalarPrediction'

            elif layer_type == 'Embedding':
                assert 'weights_embeddings' not in model_info, "Model has too many embeddings layers"
                model_info['weights_embeddings'] = weights
                model_info['input_size'] = layer.get_config()['output_dim']
                model_info['input_dim'] = layer.get_config()['input_dim']
                model_info['input_length'] = layer.get_config()['input_length']

            elif layer_type in ['SimpleRNN', 'GRU', 'LSTM']:
                assert 'type' not in model_info, 'Model has too many recurrent layers' 
                model_info['recurrent_layer'] = layer_type
                model_info['weights_recurrent'] = weights
                model_info['size_hidden'] = layer.output_dim

            else:
                if weights != []:
                    model_info['classifiers'][layer.name] = weights
                
        return model_info

    def visualise_embeddings(self):
        raise NotImplementedError()

    def save_model(self, filename):
        """
        Save model to file
        """
        # check if filename exists
        exists = os.path.exists(filename+'.h5')
        while exists:
            overwrite = raw_input("Filename exists, overwrite? (y/n)")
            if overwrite == 'y':
                exists = False
                continue
            filename = raw_input("Provide filename (without extension)")
              
        # save file
        self.model.save(filename)

    def plot_loss(self, save_to_file=False):
        """
        Plot loss on the last training
        of the network.
        """
        plt.plot(self.trainings_history.losses, label='Training set')
        plt.plot(self.trainings_history.val_losses, label='Validation set')
        plt.title("Loss during last training")
        plt.xlabel("Epoch")
        plt.ylabel(self.loss_function)
        plt.axhline(xmin=0)
        plt.legend()
        plt.show()

    def plot_metrics_training(self, save_to_file=False):
        """
        Plot the prediction error during the last training
        round of the network
        :param save_to_file:    file name to save file to
        """
        for metric in self.metrics:
            plt.plot(self.trainings_history.metrics_train[metric], label="%s training set" % metric)
            plt.plot(self.trainings_history.metrics_val[metric], label="%s validation set" % metric)

        plt.title("Monitors metrics during training")
        plt.xlabel("Epoch")
        plt.axhline(xmin=0)
        plt.ylabel("")
        plt.legend(loc=3)
        plt.show()

    def plot_esp(self):
        """
        Plot the spectral radius of the recurrent connections
        of the network during training
        """
        plt.plot(self.trainings_history.esp)
        plt.title("Spectral radius of recurrent connections")
        plt.xlabel("Epoch")
        plt.ylabel("spectral radius")
        plt.show()

    def plot_embeddings(self):
        """
        Plot embeddings of the network (only available for
        2 dimensional embeddings)
        :return:
        """
        weights = self.model.layers[1].get_weights()[0]
        assert weights.shape[1] == 2, "visualise embeddings only available for 2d embeddings"
        # find limits
        xmin, ymin = 1.1 * weights.max(axis=0)
        xmax, ymax = 1.1 * weights.min(axis=0)
        # use dmap to determine labels
        dmap_inverted = dict(zip(self.dmap.values(), self.dmap.keys()))
        for i in xrange(1, len(weights)):
            xy = tuple(weights[i])
            x, y = xy
            plt.plot(x, y, 'o')
            plt.annotate(dmap_inverted[i], xy=xy)
            plt.xlim([xmin,xmax])
            plt.ylim([ymin,ymax])
            i += 1
        plt.show()

    def generate_callbacks(self, plot_embeddings, print_every, recurrent_id, embeddings_id, save_every, filename):
        """
        Generate sequence of callbacks to use during training
        :param recurrent_id:
        :param weights_animation:           set to true to generate visualisation of embeddings
        :param plot_embeddings:             generate scatter plot of embeddings every plot_embeddings epochs
        :param print_every:                 print summary of results every print_every epochs
        :return:
        """

        history = TrainingHistory(metrics=self.metrics, recurrent_id=recurrent_id, param_id=1, save_every=save_every, filename=filename)
        callbacks = [history]

        if plot_embeddings:
            if plot_embeddings is True:
                embeddings_plot = VisualiseEmbeddings(self.dmap, embeddings_id=embeddings_id)
                callbacks.append(embeddings_plot)
            else:
                pass

        return callbacks

    def data_from_treebank(self, treebank, format='infix', pad_to=None):
        raise NotImplementedError("Should be implemented in subclass")

    @staticmethod
    def get_embeddings_layer_id():
        raise NotImplementedError("Should be implemented in subclass")

    @staticmethod
    def get_recurrent_layer_id():
        raise NotImplementedError("Should be implemented in subclass")


class ScalarPrediction(Training):
    """
    Give description.
    """
    def __init__(self, digits=np.arange(-10,11), operators=['+', '-']):
        # run superclass init
        super(ScalarPrediction, self).__init__(digits=digits, operators=operators)

        # set loss and metric functions
        self.loss_function = 'mean_squared_error'
        self.metrics = ['mean_absolute_error', 'mean_squared_error', 'binary_accuracy']

    def _build(self, W_embeddings, W_recurrent, W_classifier):
        """
        Build the trainings architecture around
        the model.
        """
        # create input layer
        input_layer = Input(shape=(self.input_length,), dtype='int32', name='input')

        # create embeddings
        embeddings = Embedding(input_dim=self.input_dim, output_dim=self.input_size,
                               input_length=self.input_length, weights=W_embeddings,
                               trainable=self.train_embeddings,
                               mask_zero=self.mask_zero,
                               name='embeddings')(input_layer)


        # create recurrent layer
        recurrent = self.recurrent_layer(self.size_hidden, name='recurrent_layer',
                                         weights=W_recurrent,
                                         trainable=self.train_embeddings,
                                         dropout_U=self.dropout_recurrent)(embeddings)

        # create output layer
        if W_classifier is not None:
            W_classifier = W_classifier['output'] 
        output_layer = Dense(1, activation='linear', weights=W_classifier,
                             trainable=self.train_classifier, name='output')(recurrent)

        # create model
        self.model = ArithmeticModel(input=input_layer, output=output_layer, dmap=self.dmap)

    def data_from_treebank(self, treebank, format='infix', pad_to=None):
        """
        Generate test data from a MathTreebank object.
        """
        X, Y = [], []
        pad_to = pad_to or self.input_length
        for expression, answer in treebank.examples:
            input_seq = [self.dmap[i] for i in expression.to_string(format).split()]
            answer = answer
            X.append(input_seq)
            Y.append(answer)

        # pad sequences to have the same length
        assert pad_to is None or len(X[0]) <= pad_to, 'length test is %i, max length is %i. Test sequences should not be truncated' % (len(X[0]), pad_to)
        X_padded = keras.preprocessing.sequence.pad_sequences(X, dtype='int32', maxlen=pad_to)
        X = {'input':X_padded}
        Y = {'output':np.array(Y)}

        return X, Y

    @staticmethod
    def get_embeddings_layer_id():
        """
        Return embeddings layer ID
        :return: (int) id of embeddings layer
        """
        return 1


    @staticmethod
    def get_recurrent_layer_id():
        """
        Return recurrent layer ID
        :return: (int) id of recurrent layer
        """
        return 2


class ComparisonTraining(Training):
    """
    Give description.
    """
    def __init__(self, digits=np.arange(-10,11), operators=['+', '-']):
        # run superclass init
        super(ComparisonTraining, self).__init__(digits=digits, operators=operators)

        # set loss and metric functions
        self.loss_function = 'categorical_crossentropy'
        # self.loss_function = 'mean_squared_error'

        self.metrics = ['categorical_accuracy']

    def _build(self, W_embeddings, W_recurrent, W_classifier={'output':None}):
        """
        Build the trainings architecture around
        the model.
        """
        # create input layer
        input1 = Input(shape=(self.input_length,), dtype='int32', name='input1')
        input2 = Input(shape=(self.input_length,), dtype='int32', name='input2')

        # create embeddings
        embeddings = Embedding(input_dim=self.input_dim, output_dim=self.input_size,
                               input_length=self.input_length, weights=W_embeddings,
                               mask_zero=self.mask_zero, trainable=self.train_embeddings,
                               name='embeddings')

        # create recurrent layer
        recurrent = self.recurrent_layer(self.size_hidden, name='recurrent_layer',
                                         weights=W_recurrent,
                                         trainable=self.train_recurrent,
                                         dropout_U=self.dropout_recurrent)

        embeddings1 = embeddings(input1)
        embeddings2 = embeddings(input2)

        recurrent1 = recurrent(embeddings1)
        recurrent2 = recurrent(embeddings2)

        concat = merge([recurrent1, recurrent2], mode='concat', concat_axis=-1)

        # create output layer
        if W_classifier is not None:
            W_classifier = W_classifier['output']
        output_layer = Dense(3, activation='softmax', 
                             trainable=self.train_recurrent,
                             weights=W_classifier, name='output')(concat)

        # create model
        self.model = ArithmeticModel(input=[input1, input2], output=output_layer, dmap=self.dmap)

    def data_from_treebank(self, treebank, format='infix', pad_to=None):
        """
        Generate data from MathTreebank object.
        """
        # create empty input and targets
        X1, X2, Y = [], [], []
        pad_to = pad_to or self.input_length

        # loop over examples
        for example1, example2, compare in treebank.paired_examples():
            input_seq1 = [self.dmap[i] for i in example1.to_string(format).split()]
            input_seq2 = [self.dmap[i] for i in example2.to_string(format).split()]
            answer = np.zeros(3)
            answer[np.argmax([compare == '<', compare == '=',  compare == '>'])] = 1
            X1.append(input_seq1)
            X2.append(input_seq2)
            Y.append(answer)

        # pad sequences to have the same length
        assert pad_to is None or len(X1[0]) <= pad_to, 'length test is %i, max length is %i. Test sequences should not be truncated' % (len(X1[0]), pad_to)
        X1_padded = keras.preprocessing.sequence.pad_sequences(X1, dtype='int32', maxlen=pad_to)
        X2_padded = keras.preprocessing.sequence.pad_sequences(X2, dtype='int32', maxlen=pad_to)

        X_padded = {'input1':X1_padded, 'input2': X2_padded}
        Y = {'output': np.array(Y)}

        return X_padded, Y

    @staticmethod
    def get_embeddings_layer_id():
        """
        Return embeddings layer ID
        :return: (int) id of embeddings layer
        """
        return 2


    @staticmethod
    def get_recurrent_layer_id():
        """
        Return recurrent layer ID
        :return: (int) id of recurrent layer
        """
        return 3

class Seq2Seq(Training):
    """
    Class to do sequence to sequence training.
    """
    def __init__(self, digits=np.arange(-10,11), operators=['+', '-']):
        # run superclass init
        super(Seq2Seq, self).__init__(digits=digits, operators=operators)

        # set loss and metric functions
        # set loss function and metrics
        self.loss_function = {'output': 'mean_squared_error'}
        self.metrics = ['mean_absolute_error', 'mean_squared_error', 'binary_accuracy']

    def _build(self, W_embeddings, W_recurrent, W_classifier):
        """
        Build model
        """

        # create input layer
        input_layer = Input(shape=(self.input_length,), dtype='int32', name='input')

        # create embeddings
        embeddings = Embedding(input_dim=self.input_dim, output_dim=self.input_size,
                               input_length=self.input_length, weights=W_embeddings,
                               trainable=True,
                               mask_zero=self.mask_zero,
                               name='embeddings')(input_layer)

        # create recurrent layer
        recurrent = self.recurrent_layer(self.size_hidden, name='recurrent_layer',
                                         weights=W_recurrent,
                                         trainable=True,
                                         return_sequences=True,
                                         dropout_U=self.dropout_recurrent)(embeddings)

        mask = TimeDistributed(Masking(mask_value=0.0))(recurrent)

        if W_classifier is not None:
            W_classifier = W_classifier['output']
        output = TimeDistributed(Dense(1, activation='linear'), name='output')(mask)

        self.model = ArithmeticModel(input=input_layer, output=output, dmap=self.dmap)

    def data_from_treebank(self, treebank, format='infix', pad_to=None):
        """
        Generate test data from a MathTreebank object.
        """
        # create dictionary with outputs
        X, Y = [], []
        pad_to = pad_to or self.input_length

        # loop over examples
        for expression, answer in treebank.examples:
            expression.get_targets(format, 'intermediate_locally')
            input_seq = [self.dmap[i] for i in expression.to_string(format).split()]
            X.append(input_seq)
            Y.append(expression.targets['intermediate_locally'])

        # pad sequences to have the same length
        assert pad_to is None or len(X[0]) <= pad_to, 'length test is %i, max length is %i. Test sequences should not be truncated' % (len(X[0]), pad_to)
        X_padded = keras.preprocessing.sequence.pad_sequences(X, dtype='int32', maxlen=pad_to)
        Y_padded = keras.preprocessing.sequence.pad_sequences(Y, maxlen=pad_to, dtype='float32')

        X = {'input': X_padded}
        Y = {'output': Y_padded}


        return X, Y

    @staticmethod
    def get_embeddings_layer_id():
        """
        Return embeddings layer ID
        :return (int) id of embeddings layer
        """
        return 1


    @staticmethod
    def get_recurrent_layer_id():
        """
        return recurrent layer ID
        :return (int) id of recurrent layer
        """
        return 2


class DiagnosticClassifier(Training):
    """
    Retrain an already trained model with new classifiers to
    test what information is extratable from the representations
    the model generates.
    """
    def __init__(self, digits=np.arange(-10,11), operators=['+', '-'], model=None, classifiers=None):
        # run superclass init
        super(DiagnosticClassifier, self).__init__(digits=digits, operators=operators)

        # set loss and metric functions
        self.loss = {
                'grammatical': 'binary_crossentropy',
                'intermediate_locally': 'mean_squared_error',
                'subtracting':'binary_crossentropy',
                'minus1depth':'binary_crossentropy',
                'minus2depth':'binary_crossentropy',
                'minus3depth':'binary_crossentropy',
                'minus4depth':'binary_crossentropy',
                'intermediate_recursively':'mean_squared_error',
                'intermediate_directly': 'mean_squared_error',
                'depth': 'mse'
                    }

        self.metrics = {
                'grammatical': ['binary_accuracy'], 
                'intermediate_locally': ['mean_absolute_error', 'mean_squared_error', 'binary_accuracy'],
                'subtracting': ['binary_accuracy'],
                'minus1depth': ['binary_accuracy'],
                'minus2depth': ['binary_accuracy'],
                'minus3depth': ['binary_accuracy'],
                'minus4depth': ['binary_accuracy'],
                'intermediate_recursively': ['mean_absolute_error', 'mean_squared_error', 'binary_accuracy'],
                'intermediate_directly': ['mean_absolute_error', 'mean_squared_error', 'binary_accuracy'],
                'depth': ['mean_squared_error', 'binary_accuracy'],
                    }  

        self.activations = {
                'grammatical':'sigmoid',
                'intermediate_locally': 'linear',
                'intermediate_directly': 'linear',
                'subtracting': 'sigmoid',
                'minus1depth': 'sigmoid',
                'minus2depth': 'sigmoid',
                'minus3depth': 'sigmoid',
                'minus4depth': 'sigmoid',
                'intermediate_recursively':'linear',
                'depth': 'linear'}

        self.output_size = {
                'grammatical':1,
                'intermediate_locally': 1,
                'intermediate_directly': 1,
                'subtracting':1,
                'minus1depth':1,
                'minus2depth':1,
                'minus3depth':1,
                'minus4depth':1,
                'intermediate_recursively':1,
                'depth':1}

        # set classifiers and attributes
        self.classifiers = classifiers
        self.set_attributes()

        # add model
        self.add_pretrained_model(model, copy_weights=['recurrent', 'embeddings', 'classifier'], classifiers=classifiers)

    def _build(self, W_embeddings, W_recurrent, W_classifier):
        """
        Build model with given embeddings and recurren weights.
        """

        # create input layer
        input_layer = Input(shape=(self.input_length,), dtype='int32', name='input')


        # create embeddings
        embeddings = Embedding(input_dim=self.input_dim, output_dim=self.input_size,
                               input_length=self.input_length, weights=W_embeddings,
                               trainable=False,
                               mask_zero=self.mask_zero,
                               name='embeddings')(input_layer)

        # create recurrent layer
        recurrent = self.recurrent_layer(self.size_hidden, name='recurrent_layer',
                                         weights=W_recurrent,
                                         trainable=False,
                                         return_sequences=True,
                                         dropout_U=self.dropout_recurrent)(embeddings)

        mask = TimeDistributed(Masking(mask_value=0.0))(recurrent)
        
        # add classifier layers
        classifiers = []
        for classifier in self.classifiers:
            try:
                weights = W_classifier[classifier]
            except TypeError:
                weights = None
            classifiers.append(TimeDistributed(Dense(self.output_size[classifier], activation=self.activations[classifier], weights=weights), name=classifier)(mask))

        # create model
        self.model = ArithmeticModel(input=input_layer, output=classifiers, dmap=self.dmap)

    def set_attributes(self):
        """
        Set the classifiers that should be trained and their
        corresponding lossfunctions, metrics and output sizes
        as attributes to the class.
        """
        self.loss_function = dict([(key, self.loss[key]) for key in self.classifiers])
        self.metrics = dict([(key, self.metrics[key]) for key in self.classifiers])
        self.output_size = dict([(key, self.output_size[key]) for key in self.classifiers])
        self.activations = dict([(key, self.activations[key]) for key in self.classifiers])


    def data_from_treebank(self, treebank, format='infix', pad_to=None):
        """
        Generate test data from a MathTreebank object.
        """
        # create dictionary with outputs
        X, Y = [], dict([(classifier, []) for classifier in self.classifiers]) 
        pad_to = pad_to or self.input_length

        # loop over examples
        for expression, answer in treebank.examples:
            expression.get_targets(format, *self.classifiers)
            input_seq = [self.dmap[i] for i in expression.to_string(format).split()]
            X.append(input_seq)
            for classifier in self.classifiers:
                target = expression.targets[classifier]
                Y[classifier].append(target)
        # pad sequences to have the same length
        assert pad_to is None or len(X[0]) <= pad_to, 'length test is %i, max length is %i. Test sequences should not be truncated' % (len(X[0]), pad_to)
        X_padded = keras.preprocessing.sequence.pad_sequences(X, dtype='int32', maxlen=pad_to)

        # make numpy arrays from Y data
        for output in Y:
            Y[output] = np.array(keras.preprocessing.sequence.pad_sequences(Y[output], maxlen=pad_to))

        X = {'input': X_padded}

        return X, Y

    @staticmethod
    def get_embeddings_layer_id():
        """
        Return embeddings layer ID
        :return (int) id of embeddings layer
        """
        return 1


    @staticmethod
    def get_recurrent_layer_id():
        """
        return recurrent layer ID
        :return (int) id of recurrent layer
        """
        return 2

