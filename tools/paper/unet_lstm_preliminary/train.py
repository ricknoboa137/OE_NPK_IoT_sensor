"""Retrain the preliminary UNet-LSTM exactly as coded in the notebook.

Copied from Weather_Stations_DataAnalysis.ipynb (WREN repository, commit d890286):
cell 31 (metrics, data preparation, model), cell 32 (sequences, compilation,
training, history plot) and cell 33 (prediction samples). The code is kept as it
was, including the parts that the later work revised; only file locations, the
training settings recorded by the run, and an optional seed are added.

Training settings. The notebook cell shows epochs = 10 and batch_size = 5, but it
was edited after the run: the recorded log has 20 epochs of 19 steps, which with
validation_split = 0.3 of the 163 sequences (114 for training) means batch_size = 6.
Those recorded settings are the defaults here.

What can and cannot be reproduced. The run did not save its trained weights, and
its prediction samples were drawn with np.random.choice without a seed, so a new
run gives a model and samples of the same kind but not the same pixels. The figures
of the original run are archived unchanged in data/unet_preliminary/ (original_*.png).

Needs TensorFlow (tf210 environment). Outputs go to data/unet_preliminary/retrained/.

    C:/Users/User/anaconda3/envs/tf210/python.exe train.py
    C:/Users/User/anaconda3/envs/tf210/python.exe train.py --epochs 1      # quick check
"""
import argparse, csv, os, sys, pathlib
import numpy as np
import tensorflow as tf
from tensorflow.keras.layers import (Input, Conv2D, MaxPooling2D, UpSampling2D, Concatenate, LSTM, Dense,
                                     TimeDistributed, Lambda, Reshape)
from tensorflow.keras.models import Model
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import paper_data

D = paper_data.DATA / "unet_preliminary"
NDMI_NODATA_VALUE = 1.0
NDMI_MIN_VALUE = -1.0
NDMI_MAX_VALUE = 1.0


# ---- cell 31: metrics -------------------------------------------------------------
class MaskedMeanAbsoluteError(tf.keras.metrics.Metric):
    def __init__(self, name="masked_mae", **kwargs):
        super().__init__(name=name, **kwargs)
        self.total_abs_error = self.add_weight(name="total_abs_error", initializer="zeros")
        self.count = self.add_weight(name="count", initializer="zeros")

    def update_state(self, y_true, y_pred, sample_weight=None):
        abs_error = tf.abs(y_true - y_pred)
        if sample_weight is not None:
            if tf.rank(sample_weight) < tf.rank(abs_error):
                sample_weight = tf.expand_dims(sample_weight, axis=-1)
            masked_abs_error = abs_error * sample_weight
        else:
            masked_abs_error = abs_error
        current_batch_sum_abs_error = tf.reduce_sum(masked_abs_error, axis=[1, 2, 3])
        if sample_weight is not None:
            current_batch_count = tf.reduce_sum(tf.cast(sample_weight, tf.float32), axis=[1, 2]) * y_true.shape[-1]
        else:
            current_batch_count = tf.cast(tf.size(abs_error) / tf.shape(abs_error)[0], tf.float32)
        self.total_abs_error.assign_add(tf.reduce_sum(current_batch_sum_abs_error))
        self.count.assign_add(tf.reduce_sum(current_batch_count))

    def result(self):
        return tf.math.divide_no_nan(self.total_abs_error, self.count)

    def reset_state(self):
        self.total_abs_error.assign(0.)
        self.count.assign(0.)


class MaskedPSNR(tf.keras.metrics.Metric):
    def __init__(self, name="masked_psnr", max_val=NDMI_MAX_VALUE, min_val=NDMI_MIN_VALUE,
                 nodata_value=NDMI_NODATA_VALUE, **kwargs):
        super().__init__(name=name, **kwargs)
        self.total_psnr = self.add_weight(name="total_psnr", initializer="zeros")
        self.num_samples = self.add_weight(name="num_samples", initializer="zeros")
        self.max_val, self.min_val, self.nodata_value = max_val, min_val, nodata_value

    def update_state(self, y_true, y_pred, sample_weight=None):
        if sample_weight is None:
            return
        mask = tf.expand_dims(sample_weight, axis=-1) if tf.rank(sample_weight) < tf.rank(y_true) else sample_weight
        masked_y_true = tf.where(tf.cast(mask, tf.bool), y_true, tf.zeros_like(y_true))
        masked_y_pred = tf.where(tf.cast(mask, tf.bool), y_pred, tf.zeros_like(y_pred))
        mse_per_pixel = tf.square(masked_y_true - masked_y_pred)
        sum_mse = tf.reduce_sum(mse_per_pixel * tf.cast(mask, tf.float32), axis=[1, 2, 3])
        num_valid_elements = tf.reduce_sum(tf.cast(mask, tf.float32), axis=[1, 2, 3])
        mse_per_image = tf.math.divide_no_nan(sum_mse, num_valid_elements)
        range_sq = (self.max_val - self.min_val) ** 2
        psnr_per_image = tf.where(mse_per_image > 1e-10,
                                  10 * tf.math.log(range_sq / mse_per_image) / tf.math.log(10.0), 100.0)
        valid_psnrs = tf.boolean_mask(psnr_per_image, num_valid_elements > 0)
        self.total_psnr.assign_add(tf.reduce_sum(valid_psnrs))
        self.num_samples.assign_add(tf.cast(tf.shape(valid_psnrs)[0], tf.float32))

    def result(self):
        return tf.math.divide_no_nan(self.total_psnr, self.num_samples)

    def reset_state(self):
        self.total_psnr.assign(0.)
        self.num_samples.assign(0.)


class MaskedSSIM(tf.keras.metrics.Metric):
    def __init__(self, name="masked_ssim", max_val=NDMI_MAX_VALUE, min_val=NDMI_MIN_VALUE,
                 nodata_value=NDMI_NODATA_VALUE, **kwargs):
        super().__init__(name=name, **kwargs)
        self.total_ssim = self.add_weight(name="total_ssim", initializer="zeros")
        self.num_samples = self.add_weight(name="num_samples", initializer="zeros")
        self.max_val, self.min_val, self.nodata_value = max_val, min_val, nodata_value

    def update_state(self, y_true, y_pred, sample_weight=None):
        if sample_weight is None:
            return
        mask = tf.expand_dims(sample_weight, axis=-1) if tf.rank(sample_weight) < tf.rank(y_true) else sample_weight
        valid_image_mask = tf.reduce_any(tf.cast(mask, tf.bool), axis=[1, 2, 3])
        y_true_valid = tf.boolean_mask(y_true, valid_image_mask)
        y_pred_valid = tf.boolean_mask(y_pred, valid_image_mask)
        mask_valid = tf.boolean_mask(mask, valid_image_mask)
        if tf.shape(y_true_valid)[0] == 0:
            return
        y_true_for_ssim = tf.where(tf.cast(mask_valid, tf.bool), y_true_valid, tf.zeros_like(y_true_valid))
        y_pred_for_ssim = tf.where(tf.cast(mask_valid, tf.bool), y_pred_valid, tf.zeros_like(y_pred_valid))
        ssim_val = tf.image.ssim(y_true_for_ssim, y_pred_for_ssim, max_image_value=(self.max_val - self.min_val))
        self.total_ssim.assign_add(tf.reduce_sum(ssim_val))
        self.num_samples.assign_add(tf.cast(tf.shape(ssim_val)[0], tf.float32))

    def result(self):
        return tf.math.divide_no_nan(self.total_ssim, self.num_samples)

    def reset_state(self):
        self.total_ssim.assign(0.)
        self.num_samples.assign(0.)


# ---- cell 31: model ---------------------------------------------------------------
def create_unet_lstm_model(input_shape, num_output_channels):
    inputs = Input(shape=input_shape)
    conv1 = TimeDistributed(Conv2D(64, 3, activation="relu", padding="same"))(inputs)
    pool1 = TimeDistributed(MaxPooling2D(pool_size=(2, 2)))(conv1)
    conv2 = TimeDistributed(Conv2D(128, 3, activation="relu", padding="same"))(pool1)
    pool2 = TimeDistributed(MaxPooling2D(pool_size=(2, 2)))(conv2)
    _, sequence_length_actual, h_pooled, w_pooled, c_pooled = pool2.shape
    lstm_input_reshaped = Reshape((sequence_length_actual, h_pooled * w_pooled * c_pooled))(pool2)
    lstm_output = LSTM(256, return_sequences=False)(lstm_input_reshaped)
    target_h, target_w, bottleneck_channels = input_shape[1] // 4, input_shape[2] // 4, 128
    bottleneck_features_dense = Dense(target_h * target_w * bottleneck_channels, activation="relu")(lstm_output)
    bottleneck = Reshape((target_h, target_w, bottleneck_channels))(bottleneck_features_dense)
    conv2_skip = Lambda(lambda x: x[:, -1, :, :, :])(conv2)
    conv1_skip = Lambda(lambda x: x[:, -1, :, :, :])(conv1)
    up1 = UpSampling2D(size=(2, 2))(bottleneck)
    concat1 = Concatenate()([up1, conv2_skip])
    conv3 = Conv2D(64, 3, activation="relu", padding="same")(concat1)
    up2 = UpSampling2D(size=(2, 2))(conv3)
    concat2 = Concatenate()([up2, conv1_skip])
    conv4 = Conv2D(32, 3, activation="relu", padding="same")(concat2)
    outputs = Conv2D(num_output_channels, 1, activation="linear")(conv4)
    return Model(inputs=inputs, outputs=outputs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=6)
    ap.add_argument("--seed", type=int, default=None, help="the original run used no seed")
    args = ap.parse_args()
    if args.seed is not None:
        np.random.seed(args.seed)
        tf.random.set_seed(args.seed)

    out = D / "retrained"
    out.mkdir(exist_ok=True)

    # cell 25 output, archived by preprocess.py; cell 26 adds the channel axis
    data_arrays = np.load(D / "ndmi_stack_preliminary.npz")["ndmi"][..., np.newaxis]

    # ---- cell 32 ----------------------------------------------------------------
    sequence_length = 3
    X_train, y_train = [], []
    for i in range(len(data_arrays) - sequence_length):
        X_train.append(np.stack(data_arrays[i:i + sequence_length]))
        y_train.append(data_arrays[i + sequence_length])
    X_train, y_train = np.array(X_train), np.array(y_train)
    print(f"X_train {X_train.shape}, y_train {y_train.shape}")
    model = create_unet_lstm_model(X_train.shape[1:], y_train.shape[-1])
    model.compile(optimizer="adam",
                  loss=tf.keras.losses.MeanSquaredError(reduction=tf.keras.losses.Reduction.SUM_OVER_BATCH_SIZE),
                  metrics=[MaskedMeanAbsoluteError(name="masked_mae"),
                           MaskedPSNR(name="masked_psnr"),
                           MaskedSSIM(name="masked_ssim")])
    print(f"parameters: {model.count_params():,}")
    history = model.fit(X_train, y_train, epochs=args.epochs, batch_size=args.batch_size, validation_split=0.3)

    with open(out / "training_log.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        keys = list(history.history)
        w.writerow(["epoch"] + keys)
        for e in range(len(history.history[keys[0]])):
            w.writerow([e + 1] + [history.history[k][e] for k in keys])

    plt.figure(figsize=(18, 6))
    for k, (train, val, title, ylabel, label) in enumerate((
            ("loss", "val_loss", "Model Loss (MSE)", "Loss", "Loss"),
            ("masked_mae", "val_masked_mae", "Model Mean Absolute Error", "MAE", "MAE"),
            ("masked_psnr", "val_masked_psnr", "Model PSNR", "PSNR", "PSNR")), 1):
        plt.subplot(1, 3, k)
        plt.plot(history.history[train], label=f"Train {label}")
        plt.plot(history.history[val], label=f"Validation {label}")
        plt.title(title)
        plt.xlabel("Epoch")
        plt.ylabel(ylabel)
        plt.legend()
        plt.grid(True)
    plt.tight_layout()
    plt.savefig(out / "training_history.png", dpi=100, bbox_inches="tight", facecolor="white")
    plt.close("all")

    # ---- cell 33 (indexing kept as in the notebook; the guard only avoids an index ----
    # ---- error when the random sample falls in the last three sequences)          ----
    sample_indices = np.random.choice(len(X_train), min(5, len(X_train)), replace=False)
    for i, idx in enumerate(sample_indices):
        input_sequence_sample = X_train[idx:idx + 1]
        true_next_image = y_train[idx + 3] if idx + 3 < len(y_train) else y_train[-1]
        predicted_next_image = model.predict(input_sequence_sample)[0]
        num_subplots = sequence_length + 2
        plt.figure(figsize=(num_subplots * 3, 4))
        for j in range(sequence_length):
            plt.subplot(1, num_subplots, j + 1)
            plt.imshow((input_sequence_sample[0, j, :, :, 0]) * 255, cmap="gray")
            plt.title(f"Input T-{sequence_length - j - 1}")
            plt.axis("off")
        plt.subplot(1, num_subplots, sequence_length + 1)
        plt.imshow(true_next_image[:, :, 0], cmap="gray")
        plt.title("True Next Image")
        plt.axis("off")
        plt.subplot(1, num_subplots, sequence_length + 2)
        plt.imshow(np.clip(predicted_next_image, -1, 1)[:, :, 0], cmap="gray")
        plt.title("Predicted Next Image")
        plt.axis("off")
        plt.suptitle(f"Sample {i + 1}: Input Sequence, True Next, and Predicted Next Image", fontsize=16)
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.savefig(out / f"prediction_sample_{i + 1}.png", dpi=100, bbox_inches="tight", facecolor="white")
        plt.close("all")
    print(f"outputs written to {out}")


if __name__ == "__main__":
    main()
