from keras.models import Model, model_from_json
from keras.layers import Embedding, Dense, Input, merge, SimpleRNN, GRU, LSTM
import keras.preprocessing.sequence
from generate_training_data import generate_treebank, parse_language
from arithmetics import mathTreebank
from TrainingHistory import TrainingHistory
from DrawWeights import DrawWeights
from PlotEmbeddings import PlotEmbeddings
from Logger import Logger
import matplotlib.pyplot as plt
import numpy as np
import random


class Training(object):
    """
    Give elaborate description
    """
    def __init__(self):
        """
        Create training architecture
        """
        raise NotImplementedError

    def generate_model(self, recurrent_layer, input_dim, input_size, input_length,
                       size_hidden, dmap,
                       W_embeddings=None, W_recurrent=None, W_classifier=None,
                       train_classifier=True, train_embeddings=True, 
                       train_recurrent=True,
                       mask_zero=True, dropout_recurrent=0.0,
                       optimizer='adagrad'):
        """
        Generate the model to be trained
        :param recurrent_layer:     type of recurrent layer (from keras.layers SimpleRNN, GRU or LSTM)
        :param input_dim:           vocabulary size
        :param input_size:          dimensionality of the embeddings (input size recurrent layer)
        :param input_length:        max sequence length
        :param size_hidden:         size recurrent layer
        :param W_embeddings:        Either an embeddings matrix or None if to be generated by keras layer
        :param W_recurrent:         Either weights for the recurrent matrix or None if to be generated by keras layer
        :param W_classifier:        Either weights for the classifier or None if to be generated by keras layer
        :param dmap:                A map from vocabulary words to integers
        :param train_embeddings:    set to false to fix embedding weights during training
        :param train_classifier:    set to false to fix classifier layer weights during training
        :param train_recurrent:     set to false to fix recurrent weights during training
        :param mask_zero:           set to true to mask 0 values
        :param dropout_recurrent:   dropout param for recurrent weights
        :param optimizer:           optimizer to use during training
        :return:
        """

        # set network attributes
        self.recurrent_layer = recurrent_layer
        self.input_dim = input_dim
        self.input_size = input_size
        self.input_length = input_length
        self.size_hidden = size_hidden
        self.dmap = dmap
        self.train_classifier = train_classifier
        self.train_embeddings = train_embeddings
        self.train_recurrent = train_recurrent
        self.mask_zero = mask_zero
        self.dropout_recurrent = dropout_recurrent
        self.optimizer = optimizer
        self.trainings_history = None
        self.model = None

        # build model
        self._build(W_embeddings, W_recurrent, W_classifier)

    def _build(self, W_embeddings, W_recurrent, W_classifier):
        raise NotImplementedError()

    def add_pretrained_model(self, json_model, model_weights, dmap, copy_weights=['recurrent','embeddings','classifier'], train_classifier=True, train_embeddings=True, train_recurrent=True, mask_zero=True, dropout_recurrent=0.0, optimizer='adam'):
        """
        Add a model with already trained weights. Model can be originally
        from a different training architecture, check which weights should be
        copied.
        :param json_model:      json filename containing model architecture
        :param model_weights:   h5 file containing model weights
        :param optimizer:       optimizer to use during training
        :param copy_weights:    determines which weights should be copied
        """

        model_info = self.get_model_info(json_model, model_weights)

        # find recurrent layer
        recurrent_layer = {'SimpleRNN': SimpleRNN, 'GRU': GRU, 'LSTM': LSTM}[model_info['recurrent_layer']]

        W_recurrent, W_embeddings, W_classifier = None, None, None

        # override weights with model weights
        if 'recurrent' in copy_weights:
            W_recurrent = model_info['weights_recurrent']

        if 'embeddings' in copy_weights:
            W_embeddings = model_info['weights_embeddings']

        if 'classifier' in copy_weights:
            W_classifier = model_info['weights_classifier']
            assert model_info['architecture'] == type(self).__name__

        # run build function
        self.generate_model(recurrent_layer=recurrent_layer, input_dim=model_info['input_dim'], input_size=model_info['input_size'], input_length=model_info['input_length'], size_hidden=model_info['size_hidden'], W_embeddings=W_embeddings, W_recurrent=W_recurrent, W_classifier=W_classifier, dmap=dmap, train_classifier=train_classifier, train_embeddings=train_embeddings, train_recurrent=train_recurrent)
        self._build(W_embeddings, W_recurrent, W_classifier)

        return

    def model_summary(self):
        print(self.model.summary())

    def get_model_info(self, json_model, model_weights):
        """
        Get different type of weights from a json model. Check
        if network falls in family of networks that we are
        studying in this project: one layer recurrent neural
        networks that are trained in one of the architectures
        from this class A1 or A2.
        """
        model = model_from_json(open(json_model).read())
        model.load_weights(model_weights)

        # check if model is of correct type TODO
        n_layers = len(model.layers)
        assert (n_layers == 6 or n_layers == 4)

        # create list with layer objects

        model_info = {}
        # loop through layers to get weight matrices

        for n_layer in xrange(n_layers):
            layer = model.layers[n_layer]
            layer_type = model.get_config()['layers'][n_layer]['class_name']
            weights = layer.get_weights()

            if layer_type == 'InputLayer':
                # decide on architecture by checking # of input layers
                if 'architecture' in model_info:
                    model_info['architecture'] = 'A4'
                else:
                    model_info['architecture'] = 'A1'

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

            if layer_type == 'Dense':
                assert 'weights_classifier' not in model_info, "Model has too many dense layers"
                
                assert (model_info['architecture'] == 'A4' and layer.output_dim == 3) or (model_info['architecture'] == 'A1' and layer.output_dim == 1), 'Model architecture does not match, architecture is %s and output shape is %i' % (model_info['architecture'], layer.output_shape)
                model_info['weights_classifier'] = weights

        return model_info

    def visualise_embeddings(self):
        raise NotImplementedError()

    def save_to_file(self, filename):
        """Save model to file"""
        json_string = self.model.to_json()
        f = open(filename, 'w')
        f.write(json_string)
        self.model.save(filename+'_weights.h5')
        f.close()

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

    def generate_callbacks(self, weights_animation, plot_embeddings, print_every, recurrent_id,
                           embeddings_id):
        """
        Generate sequence of callbacks to use during training
        :param recurrent_id:
        :param weights_animation:        set to true to generate visualisation of embeddings
        :param plot_embeddings:             generate scatter plot of embeddings every plot_embeddings epochs
        :param print_every:                 print summary of results every print_every epochs
        :return:
        """

        history = TrainingHistory(metrics=self.metrics, recurrent_id=recurrent_id, param_id=1)
        callbacks = [history]

        if weights_animation:
            layer_id, param_id = weights_animation
            draw_weights = DrawWeights(figsize=(4, 4), layer_id=layer_id, param_id=param_id)
            callbacks.append(draw_weights)

        if plot_embeddings:
            if plot_embeddings == True:
                pass
            else:
                embeddings_plot = PlotEmbeddings(plot_embeddings, self.dmap, embeddings_id=embeddings_id)
                callbacks.append(embeddings_plot)

        if print_every:
            logger = Logger(print_every)
            callbacks.append(logger)

        return callbacks


class A1(Training):
    """
    Give description.
    """
    def __init__(self):
        self.loss_function = 'mean_squared_error'
        self.metrics = ['mean_squared_prediction_error']

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
        # TODO linear activation?
        output_layer = Dense(1, activation='linear', weights=W_classifier,
                             trainable=self.train_classifier, name='output')(recurrent)

        # create model
        self.model = Model(input=input_layer, output=output_layer)

        # compile
        self.model.compile(loss={'output': self.loss_function}, optimizer=self.optimizer,
                           metrics=self.metrics)


    def train(self, training_data, batch_size, epochs, validation_split=0.1, validation_data=None,
              verbosity=1, weights_animation=False, plot_embeddings=False, logger=False):
        """
        Fit the model.
        :param weights_animation:    Set to true to create an animation of the development of the embeddings
                                        after training.
        :param plot_embeddings:        Set to N to plot the embeddings every N epochs, only available for 2D
                                        embeddings.
        """
        X_train, Y_train = training_data

        callbacks = self.generate_callbacks(weights_animation, plot_embeddings, logger, recurrent_id=2,
                                            embeddings_id=1)

        # fit model
        self.model.fit({'input': X_train}, {'output': Y_train}, validation_data=validation_data,
                       validation_split=validation_split, batch_size=batch_size, nb_epoch=epochs,
                       callbacks=callbacks, verbose=verbosity, shuffle=True)

        self.trainings_history = callbacks[0]            # set trainings_history as attribute

    @staticmethod
    def generate_training_data(languages, dmap, digits, pad_to=None):
        """
        Take a dictionary that maps languages to number of sentences and
         return numpy arrays with training data.
        :param languages:       dictionary mapping languages (str name) to numbers
        :param pad_to:          length to pad training data to
        :return:                tuple, input, output, number of digits, number of operators
                                map from input symbols to integers
        """
        # generate treebank with examples
        treebank = generate_treebank(languages, digits=digits)
        random.shuffle(treebank.examples)

        # create empty input and targets
        X, Y = [], []

        # loop over examples
        for expression, answer in treebank.examples:
            input_seq = [dmap[i] for i in str(expression).split()]
            answer = answer
            X.append(input_seq)
            Y.append(answer)

        # pad sequences to have the same length
        assert pad_to is None or len(X[0]) <= pad_to, 'length test is %i, max length is %i. Test sequences should not be truncated' % (len(X[0]), pad_to)
        X_padded = keras.preprocessing.sequence.pad_sequences(X, dtype='int32', maxlen=pad_to)

        return X_padded, np.array(Y)

    @staticmethod
    def generate_test_data(languages, dmap, digits, pad_to=None, test_separately=True):
        """
        Take a dictionary that maps language names to number of sentences and return numpy array
        with test data.
        :param languages:       dictionary mapping language names to numbers
        :param pad_to:          desired length of test sequences
        :return:                list of tuples containing test set sames, inputs and targets
        """
        # TODO reuse training data function
        if test_separately:
            test_data = []
            for name, N in languages.items():
                X, Y = A1.generate_training_data({name: N}, dmap, digits, pad_to=pad_to)
                test_data.append((name, X, Y))

        else:
            X, Y = A1.generate_training_data(languages, dmap, digits, pad_to=pad_to)
            name = ', '.join(languages.keys())
            test_data = [(name, X, Y)]

        return test_data

    @staticmethod
    def get_recurrent_layer_id():
        """
        Return recurrent layer ID
        :return: (int) id of recurrent layer
        """
        return 2


class A4(Training):
    """
    Give description.
    """
    def __init__(self):
        self.loss_function = 'categorical_crossentropy'
        # self.loss_function = 'mean_squared_error'

        self.metrics = ['categorical_accuracy']

    def _build(self, W_embeddings, W_recurrent, W_classifier):
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
        output_layer = Dense(3, activation='softmax', 
                             trainable=self.train_recurrent,
                             weights=W_classifier, name='output')(concat)

        # create model
        self.model = Model(input=[input1, input2], output=output_layer)

        # compile
        self.model.compile(loss={'output': self.loss_function}, optimizer=self.optimizer,
                           metrics=self.metrics)

        # print(self.model.summary())


    def train(self, training_data, batch_size, epochs, validation_split=0.1, validation_data=None,
              verbosity=1, weights_animation=False, plot_embeddings=False, logger=False):
        """
        Fit the model.
        :param embeddings_animation:    Set to true to create an animation of the development of the embeddings
                                        after training.
        :param plot_embeddings:        Set to N to plot the embeddings every N epochs, only available for 2D
                                        embeddings.
        """
        X_train, Y_train = training_data

        X1_train, X2_train = X_train

        callbacks = self.generate_callbacks(weights_animation, plot_embeddings, logger, recurrent_id=3,
                                            embeddings_id=2)

        # fit model
        self.model.fit([X1_train, X2_train], {'output': Y_train}, validation_data=None,
                       validation_split=validation_split, batch_size=batch_size, nb_epoch=epochs,
                       callbacks=callbacks, verbose=verbosity, shuffle=True)

        self.trainings_history = callbacks[0]            # set trainings_history as attribute

    @staticmethod
    def generate_training_data(languages, dmap, digits, pad_to=None):
        """
        Take a dictionary that maps languages to number of sentences and
         return numpy arrays with training data.
        :param languages:       dictionary mapping languages (str name) to numbers
        :param pad_to:          length to pad training data to
        :return:                tuple, input, output, number of digits, number of operators
                                map from input symbols to integers
        """
        # generate treebank with examples
        treebank1 = generate_treebank(languages, digits=digits)
        random.shuffle(treebank1.examples)
        treebank2 = generate_treebank(languages, digits=digits)
        random.shuffle(treebank2.examples)

        # create empty input and targets
        X1, X2, Y = [], [], []

        # loop over examples
        for example1, example2 in zip(treebank1.examples, treebank2.examples):
            expr1, answ1 = example1
            expr2, answ2 = example2
            input_seq1 = [dmap[i] for i in str(expr1).split()]
            input_seq2 = [dmap[i] for i in str(expr2).split()]
            answer = np.zeros(3)
            answer[np.argmax([answ1 < answ2, answ1 == answ2, answ1 > answ2])] = 1
            X1.append(input_seq1)
            X2.append(input_seq2)
            Y.append(answer)

        # pad sequences to have the same length
        assert pad_to is None or len(X1[0]) <= pad_to, 'length test is %i, max length is %i. Test sequences should not be truncated' % (len(X1[0]), pad_to)
        X1_padded = keras.preprocessing.sequence.pad_sequences(X1, dtype='int32', maxlen=pad_to)
        X2_padded = keras.preprocessing.sequence.pad_sequences(X2, dtype='int32', maxlen=pad_to)

        X_padded = [X1_padded, X2_padded]

        return X_padded, np.array(Y)

    @staticmethod
    def generate_test_data(languages, dmap, digits, pad_to=None, test_separately=False):
        """
        Take a dictionary that maps language names to number of sentences and return numpy array
        with test data.
        :param languages:       dictionary mapping language names to numbers
        :param architecture:    architecture for which to generate test data
        :param pad_to:          desired length of test sequences
        :return:                list of tuples containing test set sames, inputs and targets
        """

        if test_separately:
            test_data = []
            for name, N in languages.items():
                X, Y = A4.generate_training_data({name: N}, dmap, digits, pad_to=pad_to)
                test_data.append((name, X, Y))

        else:
            X, Y = A4.generate_training_data(languages, dmap, digits, pad_to=pad_to)
            name = ', '.join(languages.keys())
            test_data = [(name, X, Y)]

        return test_data

    @staticmethod
    def get_recurrent_layer_id():
        """
        Return recurrent layer ID
        :return: (int) id of recurrent layer
        """
        return 3

class Probing(Training):
    """
    Retrain an already trained model with new classifiers to
    test what information is extratable from the representations
    the model generates.
    """
    def __init__(self, **classifiers):
        # TODO voeg toe: intermediate result, iets over bracket stack, andere classifiers
        loss = {'grammatical': 'binary_crossentropy'}   # TODO create a dictionary with lossfunctions for different outcomes
        metrics = {'grammatical': 'accuracy'}  # TODO create dictionary with metrics for all classifiers
        activations = {'grammatical':linear}
        output_size = {'grammatical':1}



        self.loss_functions = dict([(key, loss[key]) for key in classifiers])
        self.metrics = dict([(key, loss[key]) for key in metrics])
        self.output_size = dict([(key, loss[key]) for key in output_size])
        self.activations = dict([(key, loss[key]) for key in activations])
        self.classifiers = classifiers

    def _build(self, W_embeddings, W_recurrent, W_classifier=None):
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
                                         dropout_U=self.dropout_recurrent)(embeddings)
        
        # add classifier layers
        classifiers = []
        for classifier in self.classifiers:
            classifiers.append(Dense(self.output_size[classifier], activation=self.activations[classifier], name=classifier)(recurrent))

        # create model
        self.model = Model(input=input_layer, output=classifiers)

        self.model.compile(loss=self.loss_functions, optimizer=self.optimizer, metrics=self.metrics)(recurrent)

    def train(self, training_data, batch_size, opochs, validation_split=0.1, validation_data=None, verbosity=1):
        """
        Fit the model
        :param training data:   should be adictionary containing data fo
                                all the classifies of the network
        """
        X_train, Y_train = training_data
        
        callbacks = self.generate_callbacks(False, False, False, recurrent_id=2, embeddings_id=1)_

        self.model.fit(X_train, Y_train, validation_data=validation_data, validation_split = validation_split, batch_size=batch_size, nb_epoch=epochs, callbacks/callbacks, verbosity=verbosity, shuffle=True)

        self.trainings_History = callbacks[0]

    @staticmethod
    def generate_training_data(languages, dmap, digits, pad_to=None, classifiers):

       #generate and shuffle examples
       treebank = generate_treebank(languages, digits=digits)
       random.shuffle(treebank.examples)

       # create dictionary with outputs
       X, Y = [], dict([(classifier, []) for classifier in classifiers]) 

       # loop over examples
       for expression, answer in treebank.examples:
           expression.get_targets()
           input_seq = [dmap[i] for i in str(expression).split()]
           X.append(input_seq)
           for classifier in classifiers:
               target = expression.classifier
               Y[classifier].append(target)
               
       # pad sequences to have the same length
       assert pad_to is None or len(X1[0]) <= pad_to, 'length test is %i, max length is %i. Test sequences should not be truncated' % (len(X1[0]), pad_to)
       X_padded = keras.preprocessing.sequence.pad_sequences(X1, dtype='int32', maxlen=pad_to)

       # make numpy arrays from Y data
       for output in Y:
           Y[output] = np.array(Y[output])

       return X_padded, Y

