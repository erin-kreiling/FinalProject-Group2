


from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os

import time
import numpy as np
import tensorflow as tf
from tensorflow.python.client import device_lib
import reader
import inspect

#SOTU = open("Data/SOTU.txt", "r")
#data_path = ""/home/ubuntu/erinkreiling_finalproject

####Delete all flags before declare#####

def del_all_flags(FLAGS):
    flags_dict = FLAGS._flags()
    keys_list = [keys for keys in flags_dict]
    for keys in keys_list:
        FLAGS.__delattr__(keys)

del_all_flags(tf.flags.FLAGS)
flags = tf.flags
logging = tf.logging

flags.DEFINE_string(
    "model", "small",
    "A type of model. Possible options are: small, medium, large.")
flags.DEFINE_string("data_path", "simple-examples/data/", "data_path")
flags.DEFINE_string("save_path", None,
                    "Model output directory.")
flags.DEFINE_bool("use_fp16", False,
                  "Train using 16-bit floats instead of 32bit floats")

FLAGS = flags.FLAGS


def data_type():
  return tf.float16 if FLAGS.use_fp16 else tf.float32
class SOTUInput(object):
  """The input data."""

  def __init__(self, config, data, name=None):
    self.batch_size = batch_size = config.batch_size
    self.num_steps = num_steps = config.num_steps
    self.epoch_size = ((len(data) // batch_size) - 1) // num_steps
    self.input_data, self.targets = reader.sotu_producer(
        data, batch_size, num_steps, name=name)

class SOTUModel(object):
  """The PTB model."""

  def __init__(self, is_training, config, input_):
    self._input = input_

    batch_size = input_.batch_size
    num_steps = input_.num_steps
    size = config.hidden_size
    vocab_size = config.vocab_size

    # Slightly better results can be obtained with forget gate biases
    # initialized to 1 but the hyperparameters of the model would need to be
    # different than reported in the paper.
    def lstm_cell():
      # With the latest TensorFlow source code (as of Mar 27, 2017),
      # the BasicLSTMCell will need a reuse parameter which is unfortunately not
      # defined in TensorFlow 1.0. To maintain backwards compatibility, we add
      # an argument check here:
      if 'reuse' in inspect.getargspec(
          tf.contrib.rnn.BasicLSTMCell.__init__).args:
        return tf.contrib.rnn.BasicLSTMCell(
            size, forget_bias=0.0, state_is_tuple=True,
            reuse=tf.get_variable_scope().reuse)
      else:
        return tf.contrib.rnn.BasicLSTMCell(
            size, forget_bias=0.0, state_is_tuple=True)
    attn_cell = lstm_cell
    if is_training and config.keep_prob < 1:
      def attn_cell():
        return tf.contrib.rnn.DropoutWrapper(
            lstm_cell(), output_keep_prob=config.keep_prob)
    cell = tf.contrib.rnn.MultiRNNCell(
        [attn_cell() for _ in range(config.num_layers)], state_is_tuple=True)

    self._initial_state = cell.zero_state(batch_size, data_type())

    with tf.device("/gpu:0"):
      embedding = tf.get_variable(
          "embedding", [vocab_size, size], dtype=data_type())
      inputs = tf.nn.embedding_lookup(embedding, input_.input_data)

    if is_training and config.keep_prob < 1:
      inputs = tf.nn.dropout(inputs, config.keep_prob)

    # Simplified version of models/tutorials/rnn/rnn.py's rnn().
    # This builds an unrolled LSTM for tutorial purposes only.
    # In general, use the rnn() or state_saving_rnn() from rnn.py.
    #
    # The alternative version of the code below is:
    #
    # inputs = tf.unstack(inputs, num=num_steps, axis=1)
    # outputs, state = tf.contrib.rnn.static_rnn(
    #     cell, inputs, initial_state=self._initial_state)
    outputs = []
    state = self._initial_state
    with tf.variable_scope("RNN"):
      for time_step in range(num_steps):
        if time_step > 0: tf.get_variable_scope().reuse_variables()
        (cell_output, state) = cell(inputs[:, time_step, :], state)
        outputs.append(cell_output)

    output = tf.reshape(tf.concat(axis=1, values=outputs), [-1, size])
    softmax_w = tf.get_variable(
        "softmax_w", [vocab_size, size], dtype=data_type())
    softmax_w = tf.transpose(softmax_w)
    softmax_b = tf.get_variable("softmax_b", [vocab_size], dtype=data_type())
    logits = tf.matmul(output, softmax_w) + softmax_b
    #loss = tf.contrib.legacy_seq2seq.sequence_loss_by_example(
        #[logits],
        #[tf.reshape(input_.targets, [-1])],
        #[tf.ones([batch_size * num_steps], dtype=data_type())])
    loss = tf.nn.softmax_cross_entropy_with_logits(labels = output, logits = logits)
    self._loss = loss
    self._cost = cost = -tf.reduce_sum(loss) / batch_size
    self._final_state = state

    if not is_training:
      return

    self._lr = tf.Variable(0.0, trainable=False)
    tvars = tf.trainable_variables()
    grads, _ = tf.clip_by_global_norm(tf.gradients(cost, tvars),
                                      config.max_grad_norm)
    optimizer = tf.train.GradientDescentOptimizer(self._lr)
    self._train_op = optimizer.apply_gradients(
        zip(grads, tvars),
        global_step=tf.contrib.framework.get_or_create_global_step())

    self._new_lr = tf.placeholder(
        tf.float32, shape=[], name="new_learning_rate")
    self._lr_update = tf.assign(self._lr, self._new_lr)

  def assign_lr(self, session, lr_value):
    session.run(self._lr_update, feed_dict={self._new_lr: lr_value})

    @property
    def input(self):
        return self._input

    @property
    def initial_state(self):
        return self._initial_state

    @property
    def cost(self):
        return self._cost

    @property
    def final_state(self):
        return self._final_state

    @property
    def lr(self):
        return self._lr

    @property
    def train_op(self):
        return self._train_op

class Config(object):
  """Small config."""
  init_scale = 0.1
  learning_rate = 0.1
  max_grad_norm = 5
  num_layers = 1
  num_steps = 20
  hidden_size = 1000
  max_epoch = 1
  max_max_epoch = 10
  keep_prob = 1.0
  lr_decay = 0.5
  batch_size = 35
  vocab_size = 1000


# class MediumConfig(object):
#   """Medium config."""
#   init_scale = 0.05
#   learning_rate = 1.0
#   max_grad_norm = 5
#   num_layers = 2
#   num_steps = 35
#   hidden_size = 650
#   max_epoch = 6
#   max_max_epoch = 39
#   keep_prob = 0.5
#   lr_decay = 0.8
#   batch_size = 20
#   vocab_size = 10000
#
#
# class LargeConfig(object):
#   """Large config."""
#   init_scale = 0.04
#   learning_rate = 1.0
#   max_grad_norm = 10
#   num_layers = 2
#   num_steps = 35
#   hidden_size = 1500
#   max_epoch = 14
#   max_max_epoch = 55
#   keep_prob = 0.35
#   lr_decay = 1 / 1.15
#   batch_size = 20
#   vocab_size = 10000

def run_epoch(session, model, eval_op=None, verbose=False):
  """Runs the model on the given data."""
  start_time = time.time()
  costs = 0.0
  iters = 0
  state = session.run(model._initial_state)

  fetches = {
      "cost": model._cost,
      "final_state": model._final_state,
  }
  if eval_op is not None:
    fetches["eval_op"] = eval_op

  for step in range(model._input.epoch_size):
    feed_dict = {}
    for i, (c, h) in enumerate(model._initial_state):
      feed_dict[c] = state[i].c
      feed_dict[h] = state[i].h

    vals = session.run(fetches, feed_dict)
    cost = vals["cost"]
    state = vals["final_state"]


    costs += cost
    iters += model._input.num_steps


    if verbose and step % (model._input.epoch_size // 10) == 10:
      print("%.3f perplexity: %.3f speed: %.0f wps" %
            (step * 1.0 / model._input.epoch_size, np.exp(costs / iters),
             iters * model._input.batch_size / (time.time() - start_time)))

  return np.exp(costs / iters)


def get_config():
  return Config()
  # if FLAGS.model == "small":
  #   return SmallConfig()
  # elif FLAGS.model == "medium":
  #   return MediumConfig()
  # elif FLAGS.model == "large":
  #   return LargeConfig()
  # elif FLAGS.model == "test":
  #   return TestConfig()
  # else:
  #   raise ValueError("Invalid model: %s", FLAGS.model)


def main(_):
  if not FLAGS.data_path:
    raise ValueError("Must set --data_path to SOTU data directory")

  raw_data = reader.sotu_raw_data(FLAGS.data_path)
  train_data, valid_data, test_data, _ = raw_data

  config = get_config()
  eval_config = get_config()
  eval_config.batch_size = 1
  eval_config.num_steps = 1


  with tf.Graph().as_default():
    initializer = tf.random_uniform_initializer(-config.init_scale,
                                                config.init_scale)

    with tf.name_scope("Train"):
      train_input = SOTUInput(config=config, data=train_data, name="TrainInput")
      with tf.variable_scope("Model", reuse=None, initializer=initializer):
        m = SOTUModel(is_training=True, config=config, input_=train_input)
      tf.summary.scalar("Training Loss", m._cost)
      tf.summary.scalar("Learning Rate", m._lr)

    with tf.name_scope("Valid"):
      valid_input = SOTUInput(config=config, data=valid_data, name="ValidInput")
      with tf.variable_scope("Model", reuse=True, initializer=initializer):
        mvalid = SOTUModel(is_training=False, config=config, input_=valid_input)
      tf.summary.scalar("Validation Loss", mvalid._cost)

    with tf.name_scope("Test"):
      test_input = SOTUInput(config=eval_config, data=test_data, name="TestInput")
      with tf.variable_scope("Model", reuse=True, initializer=initializer):
        mtest = SOTUModel(is_training=False, config=eval_config,
                         input_=test_input)

    sv = tf.train.Supervisor(logdir=FLAGS.save_path)
    with sv.managed_session() as session:
      for i in range(config.max_max_epoch):
        lr_decay = config.lr_decay ** max(i + 1 - config.max_epoch, 0.0)
        m.assign_lr(session, config.learning_rate * lr_decay)

        print("Epoch: %d Learning rate: %.3f" % (i + 1, session.run(m._lr)))
        train_perplexity = run_epoch(session, m, eval_op=m._train_op,
                                     verbose=True)
        print("Epoch: %d Train Perplexity: %.3f" % (i + 1, train_perplexity))
        valid_perplexity = run_epoch(session, mvalid)
        print("Epoch: %d Valid Perplexity: %.3f" % (i + 1, valid_perplexity))

      test_perplexity = run_epoch(session, mtest)
      print("Test Perplexity: %.3f" % test_perplexity)

      if FLAGS.save_path:
        print("Saving model to %s." % FLAGS.save_path)
        sv.saver.save(session, FLAGS.save_path, global_step=sv.global_step)


if __name__ == "__main__":
  tf.app.run()


#
# def text_to_index(sentence):
#     # Remove punctuation characters except for the apostrophe
#     translator = str.maketrans('', '', string.punctuation.replace("'", ''))
#     tokens = sentence.translate(translator).lower().split()
#     return np.array([1] + [word_index[t] + index_offset if t in word_index else 2 for t in tokens])
#
#
# def print_predictions(sentences, classifier):
#   indexes = [text_to_index(sentence) for sentence in sentences]
#   x = sequence.pad_sequences(indexes,
#                              maxlen=sentence_size,
#                              padding='post',
#                              value=-1)
#   length = np.array([min(len(x), sentence_size) for x in indexes])
#   predict_input_fn = tf.estimator.inputs.numpy_input_fn(x={"x": x, "len": length}, shuffle=False)
#   predictions = [p['logistic'][0] for p in classifier.predict(input_fn=predict_input_fn)]
#   print(predictions)

# from tf.keras.preprocessing.text import
#
# tokenizer = Tokenizer()
# def generate_text(seed_text, next_words, model, max_sequence_len):
#   for _ in range(next_words):
#     #tokenizer = Tokenizer(char_level=False)
#     #tokenizer.fit_on_texts(seed_text)
#     token_list = tf.keras.preprocessing.text.Tokenizer.texts_to_sequences([seed_text])[0]
#     token_list = tf.keras.preprocessing.sequence.pad_sequences([token_list], maxlen=max_sequence_len - 1, padding='pre')
#     predicted = model.predict_classes(token_list, verbose=0)
#     output_word = ""
#     for word, index in tokenizer.word_index.items():
#       if index == predicted:
#         output_word = word
#         break
#       seed_text += " " + output_word
#     return seed_text.title()
#
# print(generate_text("better state", 4, SOTUModel, 7))