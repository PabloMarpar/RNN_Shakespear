import os
import warnings

warnings.filterwarnings("ignore")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import time
import numpy as np
import tensorflow as tf

#Shakespeare dataset
path_to_file = tf.keras.utils.get_file(
    "shakespeare.txt",
    "https://storage.googleapis.com/download.tensorflow.org/data/shakespeare.txt",
)
#reading the data
text = open(path_to_file, "rb").read().decode(encoding="utf-8")
print(f"Length of text: {len(text)} characters")
print(text[:300])
vocab = sorted(set(text))
print(f"{len(vocab)} unique characters")
#Hacemos vectores del texto
example_texts = ["abcdefg", "xyz"]

chars = tf.strings.unicode_split(example_texts, input_encoding="UTF-8")
vocab = sorted(set(text))
print(f"{len(vocab)} unique characters")
#Creamos capa de keras
example_texts = ["abcdefg", "xyz"]
chars = tf.strings.unicode_split(example_texts, input_encoding="UTF-8")
ids_from_chars = tf.keras.layers.StringLookup(
    vocabulary=list(vocab), mask_token=None
)
# COnvertimos de tokens a ids
ids = ids_from_chars(chars)
chars_from_ids = tf.keras.layers.StringLookup(
    vocabulary=ids_from_chars.get_vocabulary(), invert=True, mask_token=None
)
chars = chars_from_ids(ids)
tf.strings.reduce_join(chars, axis=-1).numpy()
def text_from_ids(ids):
    return tf.strings.reduce_join(chars_from_ids(ids), axis=-1)

## Creación de ejemplos y targets
all_ids = ids_from_chars(tf.strings.unicode_split(text, "UTF-8"))
# Creacion de dataset de ids
ids_dataset = tf.data.Dataset.from_tensor_slices(all_ids)

for ids in ids_dataset.take(10):
    print(chars_from_ids(ids).numpy().decode("utf-8"))
# Transformar caracteres sueltos en secuencia de caracteres
seq_length = 100
examples_per_epoch = len(text) // (seq_length + 1)
sequences = ids_dataset.batch(seq_length + 1, drop_remainder=True)

for seq in sequences.take(1):
    print(chars_from_ids(seq))
for seq in sequences.take(5):
    print(text_from_ids(seq).numpy())

def split_input_target(sequence):
    input_text = sequence[:-1]
    target_text = sequence[1:]
    return input_text, target_text
# Creacion de la secuencia de imputs
split_input_target(list("Tensorflow"))

dataset = sequences.map(split_input_target)

for input_example, target_example in dataset.take(1):
    print("Input :", text_from_ids(input_example).numpy())
    print("Target:", text_from_ids(target_example).numpy())

# Creacion de batches de entrenamiento
# Batch size
BATCH_SIZE = 64

BUFFER_SIZE = 10000

dataset = (
    dataset.shuffle(BUFFER_SIZE)
    .batch(BATCH_SIZE, drop_remainder=True)
    .prefetch(tf.data.experimental.AUTOTUNE)
)
## Hiperparámetros
# Construccion del modelo
vocab_size = len(vocab)
# Las dimensiones del embedding y la cantidad de unidades rnn
embedding_dim = 256
rnn_units = 1024
# CUERPO
class MyModel(tf.keras.Model):
    def __init__(self, vocab_size, embedding_dim, rnn_units):
        super().__init__(self)
        # TODO - Create an embedding layer
        self.embedding = tf.keras.layers.Embedding(vocab_size, embedding_dim)
        # TODO - Create a GRU layer
        self.gru = tf.keras.layers.GRU(
            rnn_units, return_sequences=True, return_state=True
        )
        # TODO - Finally connect it with a dense layer
        self.dense = tf.keras.layers.Dense(vocab_size)

    def call(self, inputs, states=None, return_state=False, training=False):
        x = self.embedding(inputs, training=training)
        if states is None:
            states = self.gru.get_initial_state(x)
        x, states = self.gru(x, initial_state=states, training=training)
        x = self.dense(x, training=training)

        if return_state:
            return x, states
        else:
            return x

# Unimos el modelo
model = MyModel(
    vocab_size=len(ids_from_chars.get_vocabulary()),
    embedding_dim=embedding_dim,
    rnn_units=rnn_units,
)

for input_example_batch, target_example_batch in dataset.take(1):
    example_batch_predictions = model(input_example_batch)
    print(
        example_batch_predictions.shape,
        "# (batch_size, sequence_length, vocab_size)",
    )

model.summary()

# Sampleamos
sampled_indices = tf.random.categorical(
    example_batch_predictions[0], num_samples=1
)
sampled_indices = tf.squeeze(sampled_indices, axis=-1).numpy()
# Hacemos la decodificacion, para ver lo que hace el modelo sin estar entrenado
print(sampled_indices)
print("Input:\n", text_from_ids(input_example_batch[0]).numpy())
print()
print("Next Char Predictions:\n", text_from_ids(sampled_indices).numpy())

## ENTRENAMIENTO
# TODO - add a loss function here
loss = tf.losses.SparseCategoricalCrossentropy(from_logits=True)

example_batch_mean_loss = loss(target_example_batch, example_batch_predictions)
print(
    "Prediction shape: ",
    example_batch_predictions.shape,
    " # (batch_size, sequence_length, vocab_size)",
)
print("Mean loss:        ", example_batch_mean_loss)
tf.exp(example_batch_mean_loss).numpy()
# Compilamos el modelo
model.compile(optimizer="adam", loss=loss)

# Configuramos los checkpoints
checkpoint_dir = "./checkpoint_entrenamiento"
checkpoint_prefix = os.path.join(checkpoint_dir, "ckpt_{epoch}")

checkpoint_callback = tf.keras.callbacks.ModelCheckpoint(
    filepath=checkpoint_prefix, save_weights_only=True
)

EPOCHS = 12
history = model.fit(dataset, epochs=EPOCHS, callbacks=[checkpoint_callback])
# Generamos el texto
class OneStep(tf.keras.Model):
    def __init__(self, model, chars_from_ids, ids_from_chars, temperature=1.0):
        super().__init__()
        self.temperature = temperature
        self.model = model
        self.chars_from_ids = chars_from_ids
        self.ids_from_chars = ids_from_chars

        # Create a mask to prevent "[UNK]" from being generated.
        skip_ids = self.ids_from_chars(["[UNK]"])[:, None]
        sparse_mask = tf.SparseTensor(
            # Put a -inf at each bad index.
            values=[-float("inf")] * len(skip_ids),
            indices=skip_ids,
            # Match the shape to the vocabulary
            dense_shape=[len(ids_from_chars.get_vocabulary())],
        )
        self.prediction_mask = tf.sparse.to_dense(sparse_mask)

    @tf.function
    def generate_one_step(self, inputs, states=None):
        # Convert strings to token IDs.
        input_chars = tf.strings.unicode_split(inputs, "UTF-8")
        input_ids = self.ids_from_chars(input_chars).to_tensor()

        # Run the model.
        # predicted_logits.shape is [batch, char, next_char_logits]
        predicted_logits, states = self.model(
            inputs=input_ids, states=states, return_state=True
        )
        # Only use the last prediction.
        predicted_logits = predicted_logits[:, -1, :]
        predicted_logits = predicted_logits / self.temperature
        # Apply the prediction mask: prevent "[UNK]" from being generated.
        predicted_logits = predicted_logits + self.prediction_mask

        # Sample the output logits to generate token IDs.
        predicted_ids = tf.random.categorical(predicted_logits, num_samples=1)
        predicted_ids = tf.squeeze(predicted_ids, axis=-1)

        # Convert from token ids to characters
        predicted_chars = self.chars_from_ids(predicted_ids)

        # Return the characters and model state.
        return predicted_chars, states
one_step_model = OneStep(model, chars_from_ids, ids_from_chars)
start = time.time()
states = None
next_char = tf.constant(["ROMEO:"])
result = [next_char]

for n in range(1000):
    next_char, states = one_step_model.generate_one_step(
        next_char, states=states
    )
    result.append(next_char)

result = tf.strings.join(result)
end = time.time()
print(result[0].numpy().decode("utf-8"), "\n\n" + "_" * 80)
print("\nRun time:", end - start)
start = time.time()
states = None
next_char = tf.constant(["ROMEO:", "ROMEO:", "ROMEO:", "ROMEO:", "ROMEO:"])
result = [next_char]

for n in range(1000):
    next_char, states = one_step_model.generate_one_step(
        next_char, states=states
    )
    result.append(next_char)

result = tf.strings.join(result)
end = time.time()
print(result, "\n\n" + "_" * 80)
print("\nRun time:", end - start)
# Exportamos el generador
tf.saved_model.save(one_step_model, "one_step")
one_step_reloaded = tf.saved_model.load("one_step")
states = None
next_char = tf.constant(["ROMEO:"])
result = [next_char]

for n in range(100):
    next_char, states = one_step_reloaded.generate_one_step(
        next_char, states=states
    )
    result.append(next_char)

print(tf.strings.join(result)[0].numpy().decode("utf-8"))
