## a conv2d kernel using tensorflow

import os
import warnings
import tensorflow as tf
#from tensorflow.python.eager import profiler as tfprof
import numpy as np
import argparse
import time
try:
    import pycuda.autoinit
    import pycuda as pyc
    have_pycuda=True
    print("pycuda enabled")
except:
    print("pycuda not installed")
    have_pycuda=False

#warnings.simplefilter('ignore')
#tf.logging.set_verbosity(tf.logging.ERROR)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # or any {'0', '1', '2'}
os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'
print("Eager execution: {}".format(tf.executing_eagerly()))

#    #set gpu to allow mem growth
#    gpus = tf.config.experimental.list_physical_devices('GPU')
#    if gpus:
#        try:
#            # Currently, memory growth needs to be the same across GPUs
#            for gpu in gpus:
#                tf.config.experimental.set_memory_growth(gpu, True)
#            #logical_gpus = tf.config.experimental.list_logical_devices('GPU')
#            #print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
#        except RuntimeError as e:
#            # Memory growth must be set before GPUs have been initialized
#            print(e)


def conv2d(input_data, data_format, weights, stride_, dtype):
    if data_format == "NCHW":
        input_data = tf.transpose(input_data, [0,3,1,2])
        strides = [1,1,stride_, stride_]
    else:
        strides = [1,stride_,stride_,1]
    output_data = tf.nn.conv2d(input_data, weights, strides=strides, padding='SAME', data_format=data_format)
    return output_data


#calibration measurement
def run_calibrate(input_tensor_shape, data_format, weights, stride, dtype):
    #define op
    #run the stuff
    input_image = tf.random.uniform(shape=input_tensor_shape, minval=0., maxval=1., dtype=dtype)
    _ = input_image.numpy()


#forward
def run_forward(input_tensor_shape, data_format, weights, stride, dtype):
    #define op
    input_image = tf.random.uniform(shape=input_tensor_shape, minval=0., maxval=1., dtype=dtype)
    output_result = conv2d(input_image, data_format, weights, stride, dtype)
    
    #run the stuff
    _ = output_result.numpy()


#backward
def run_backward(input_tensor_shape, data_format, weights, stride, dtype):
    #define op, under tape
    input_image = tf.random.uniform(shape=input_tensor_shape, minval=0., maxval=1., dtype=dtype)
    with tf.GradientTape(persistent=True) as tape:
        tape.watch(input_image)
        output_result = conv2d(input_image, data_format, weights, stride, dtype)
    grad_input   = tape.gradient(output_result, input_image)
    grad_weights = tape.gradient(output_result, weights)
    
    #run the stuff
    _, _ = grad_input.numpy(), grad_input.numpy()


def main(input_tensor_shape, data_format, kernel_shape, stride, dtype, n_iter, n_warm, compute_type, enable_xla):
    
    #datatype selection
    if dtype == 'float16':
        tensor_type=tf.float16
    elif dtype == 'float32':
        tensor_type=tf.float32
    else:
        raise Exception('data type can only be float16 or float32')
    
    ##XLA or not
    if tf.test.is_gpu_available():
        device = '/xla_gpu:0' if enable_xla else '/gpu:0'
    else:
        device = '/xla_cpu:0' if enable_xla else '/cpu:0'
        
    print("Running on device {}".format(device))
    #tf.config.experimental.set_memory_growth(device, True)
    #tf.config.gpu.set_per_process_memory_growth(True)

    # select commpute type
    if compute_type == "forward":
        compfunc = run_forward
    elif compute_type == "backward":
        compfunc = run_backward
    elif compute_type == "calibrate":
        compfunc = run_calibrate
    else:
        raise ValueError("Error, compute_type should be either forward or backward or calibrate")
    
    #we might need that
    with tf.device(device):
        weights = tf.Variable(tf.random.truncated_normal(kernel_shape, stddev=0.03, dtype=dtype), dtype=dtype)
    
    #start session
    print("warming up for {} steps".format(n_warm))
    with tf.device(device):
        for i in range(n_warm):
            compfunc(input_tensor_shape, data_format, weights, stride, tensor_type)
    print("done")
        
    print("running for {} steps".format(n_iter))
    start = time.time()
    #start profiling
    if have_pycuda:
        pyc.driver.start_profiler()
    with tf.device(device):
        for i in range(n_iter):
            compfunc(input_tensor_shape, data_format, weights, stride, tensor_type)

    #stop profiling
    if have_pycuda:
        pyc.driver.stop_profiler()
    end = time.time()
    print("done")
    
    duration = end-start
    print('duration {:.2f} seconds, {:.2f} seconds/call'.format(duration, duration/float(n_iter)))



if __name__ == '__main__':
    AP = argparse.ArgumentParser()
    AP.add_argument('--input_tensor_shape', type=int, nargs='+', help='the shape of the input tensor. Note that it depends on data_format (default NHWC)')
    AP.add_argument('--data_format', type=str, default='NHWC', help='choose either channels_last or channels_first')
    AP.add_argument('--kernel_shape', type=int, nargs='+', default=[5,5,3,32], help='the shape of the conv kernel [filter_height, filter_width, in_channels, out_channels]')
    AP.add_argument('--stride', type=int, default=1, help='the stride')
    AP.add_argument('--dtype', type=str, default='float32', help='the data type')
    AP.add_argument('--num_iterations', type=int, default=100, help='the number of iterations')
    AP.add_argument('--num_warmups', type=int, default=10, help='number of warmup steps')
    AP.add_argument('--compute_type', type=str, default="forward", help='forward or backward pass')
    AP.add_argument('--enable_xla', action="store_true", help="enable XLA support")
    parsed = AP.parse_args()
    
    #print args
    for arg in vars(parsed):
        print(arg, ":", getattr(parsed, arg))
        
    
    main(input_tensor_shape=parsed.input_tensor_shape,
         data_format=parsed.data_format,
         kernel_shape=parsed.kernel_shape,
         stride=parsed.stride,
         dtype=parsed.dtype,
         n_iter=parsed.num_iterations,
         n_warm=parsed.num_warmups,
         compute_type=parsed.compute_type,
         enable_xla=parsed.enable_xla)
    
    

