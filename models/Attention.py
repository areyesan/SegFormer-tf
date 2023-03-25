import tensorflow as tf
from tensorflow.keras import layers
from typing import List, Union
import numpy as np


# https://github.com/huggingface/transformers/blob/main/src/transformers/tf_utils.py
def shape_list(tensor: Union[tf.Tensor, np.ndarray]) -> List[int]:
    if isinstance(tensor, np.ndarray):
        return list(tensor.shape)
    dynamic = tf.shape(tensor)
    if tensor.shape == tf.TensorShape(None):
        return dynamic
    static = tensor.shape.as_list()
    return [dynamic[i] if s is None else s for i, s in enumerate(static)]

class Attention(tf.keras.layers.Layer):
    def __init__(self, dim, num_heads=8, qkv_bias=False, qk_scale=None, attn_drop=0., proj_drop=0., sr_ratio=1):
        super(Attention, self).__init__()
        assert dim % num_heads == 0, f"dim {dim} should be divisible by num_heads {num_heads}."

        self.dim = dim
        self.num_heads = num_heads
        head_dim = dim // num_heads
        self.scale = qk_scale or head_dim ** -0.5

        self.q = layers.Dense(dim, use_bias=qkv_bias)
        self.kv = layers.Dense(dim * 2, use_bias=qkv_bias)
        self.attn_drop = layers.Dropout(attn_drop)
        self.proj = layers.Dense(dim)
        self.proj_drop = layers.Dropout(proj_drop)

        self.sr_ratio = sr_ratio
        if sr_ratio > 1:
            self.sr = layers.Conv2D(dim, kernel_size=sr_ratio, strides=sr_ratio)
            self.norm = layers.LayerNormalization()

    def call(self, x, H, W):
        B = shape_list(x)[0]
        N = shape_list(x)[1]
        C = shape_list(x)[2]        
        q = self.q(x)
        q = tf.reshape(q, (B, N, self.num_heads, C // self.num_heads))
        q = tf.transpose(q, perm=[0, 2, 1, 3])
        if self.sr_ratio > 1:
            x_ = tf.transpose(x, perm=[0, 2, 1])
            x_ = tf.reshape(x_, (B, H, W, C))
            x_ = self.sr(x_)
            x_ = tf.reshape(x_, (B, shape_list(x_)[1]*shape_list(x_)[2], C))
            x_ = self.norm(x_)
            kv = self.kv(x_)
            kv = tf.reshape(kv, (B, shape_list(kv)[1], 2, self.num_heads, C // self.num_heads))
            kv = tf.transpose(kv, perm=[2, 0, 3, 1, 4])
        else:
            kv = self.kv(x)
            kv = tf.reshape(kv, (B, shape_list(kv)[1], 2, self.num_heads, C // self.num_heads))
            kv = tf.transpose(kv, perm=[2, 0, 3, 1, 4])

        k, v = kv[0], kv[1]
        attn = tf.matmul(q, tf.transpose(k, perm=[0, 1, 3, 2])) * self.scale
        attn = tf.nn.softmax(attn, axis=-1)
        attn = self.attn_drop(attn)

        x = tf.matmul(attn, v)
        x = tf.transpose(x, perm=[0, 2, 1, 3])
        x = tf.reshape(x, (B, N, C))
        x = self.proj(x)
        x = self.proj_drop(x)
        return x