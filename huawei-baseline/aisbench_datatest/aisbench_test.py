import os, errno
import argparse
import re
import logging
import time
from process_dataset import create_data
from config import *
logging.getLogger().setLevel(logging.INFO)


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_len', type=int, default=3500, help="input token length")
    parser.add_argument("--output_len", type=str, default="1500", help="output token length")
    parser.add_argument("--data_num", type=int, default=8192, help="dataset number")
    parser.add_argument("--concurrency", type=str, default="2048", help="concurrency")
    parser.add_argument("--request_rate", type=str, default="0", help="request rate")
    parser.add_argument("--test_type", type=str, default="stream", help="text or stream")
    parser.add_argument("--dataset", type=str, default="none", help="dataset path")
    parser.add_argument("--repeat", type=int, default=1, help="number of test repeat times")
    parser.add_argument("--enable_think", action='store_true', default=False, help="enable thinking for ds v3.1")
    parser.add_argument("--test_accuracy", action='store_true', default=False, help="test accuracy")
    return parser.parse_args()


def symlink_force(target, link_name):
    logging.info(f"make symlink: {link_name} ==> {target}")
    try:
        os.symlink(target, link_name)
    except OSError as e:
        if e.errno == errno.EEXIST:
            os.remove(link_name)
            os.symlink(target, link_name)
        else:
            raise e


if __name__ == '__main__':
    args = parse_arguments()
    input_len = args.input_len
    output_len = args.output_len
    data_num = args.data_num
    concurrency = args.concurrency
    request_rate = args.request_rate
    test_type = args.test_type
    dataset_path_input = args.dataset
    test_times = args.repeat
    enable_think = args.enable_think
    test_accuracy = args.test_accuracy

    logging.info(f"input token length: {input_len}")
    logging.info(f"output token length: {output_len}")
    logging.info(f"number of dataset: {data_num}")
    logging.info(f"concurrency: {concurrency}")
    logging.info(f"request rate: {request_rate}")
    logging.info(f"test type: {test_type}")
    logging.info(f"test_times: {test_times}")
    logging.info(f"v3.1 enable_think: {enable_think}")
    logging.info(f"accuracy test: {test_accuracy}")

    # logging.info(f"test stable performance: {stable_test}")

    # 区分流式和非流式
    if test_type == "text":
        api_test_type = "VLLMCustomAPIChat"
        api_test_abbr = "vllm-api-general-chat"
    elif test_type == "stream":
        api_test_type = "VLLMCustomAPIChatStream"
        api_test_abbr = "vllm-api-stream-chat"
    else:
        api_test_type = "VLLMCustomAPIChatStream"
        api_test_abbr = "vllm-api-stream-chat"

    if dataset_path_input == "none":
        if not os.path.exists(DATASET_PATH):
            logging.error(f"dataset work path {DATASET_PATH} not exist. please create it first.")
            exit(0)
        # 使用 gsm8k 生成数据集逻辑
        dataset_name = "GSM8K-in" + str(input_len) + "-bs" + str(data_num) + ".jsonl"
        logging.info(f"dataset_name: {dataset_name}")
        src_file = os.path.join(DATASET_PATH, dataset_name)
        # 判断数据集是否存在
        if not os.path.exists(src_file):
            logging.warning(f"Dataset {dataset_name} is not exist. Start create dataset")
            create_data(input_len, data_num, MODEL_PATH, DATASET_PATH)
            logging.info(f"Dataset {dataset_name} created.")
        else:
            logging.info(f"Dataset {dataset_name} exist.")
    else:
        # 指定数据集路径逻辑
        if not os.path.exists(dataset_path_input):
            logging.error(f"Dataset {dataset_path_input} is not exist.")
            exit(0)
        src_file = dataset_path_input

    dst_dir = os.path.join(WORK_PATH, "ais_bench/datasets/gsm8k")

    # 判断 aisbench 的 gsm8k 文件夹是否存在在
    if not os.path.exists(dst_dir):
        logging.info("dataset work path not exist. creating.")
        os.makedirs(dst_dir)
        logging.info("dataset work path created.")
    # 判断 aisbench 的 gsm8k 文件夹是否存在在 train.jsonl 文件
    train_dataset = os.path.join(dst_dir, "train.jsonl")
    if not os.path.exists(train_dataset):
        logging.info("train dataset not exist. creating.")
        file = open(train_dataset, 'w')
        file.close()
        logging.info("train dataset created.")

    dst_file = os.path.join(dst_dir, "test.jsonl")
    logging.info(f"src_file: {src_file}")
    logging.info(f"dst_file: {dst_file}")
    # 使用软连接
    symlink_force(src_file, dst_file)

    # 修改请求配置文件
    file_default = open("default_api.py", 'r+')
    file_temp = open("temp_api.py", 'w+')
    logging.info("Api config file:")
    for ss in file_default.readlines():
        tt = re.sub("model_path_for_replace", MODEL_PATH, ss)
        tt = re.sub("model_name_for_replace", MODEL_NAME, tt)
        tt = re.sub("rr_for_replace", request_rate, tt)
        tt = re.sub("test_type_for_replace", api_test_type, tt)
        tt = re.sub("test_abbr_for_replace", api_test_abbr, tt)
        tt = re.sub("ip_for_replace", HOST_IP, tt)
        tt = re.sub("port_for_replace", HOST_PORT, tt)
        tt = re.sub("outputlen_for_replace", output_len, tt)
        tt = re.sub("concurrency_for_replace", concurrency, tt)
        if test_accuracy:
            generation_kwargs = "temperature=0.6,\n\t\t\ttop_p = 0.95"
        else:
            generation_kwargs = "temperature=0,\n\t\t\tignore_eos=True"
        if enable_think:
            generation_kwargs = generation_kwargs + ",\n\t\t\tchat_template_kwargs={\"enable_thinking\": True}"
        tt = re.sub("generation_kwargs_for_replace", generation_kwargs.expandtabs(4), tt)
        print(tt, end='')
        file_temp.write(tt)
    file_default.close()
    file_temp.close()

    # 将请求配置文件软连接至 aisbench 工作目录下
    symlink_force(
        os.path.join(os.getcwd(), "temp_api.py"),
        os.path.join(WORK_PATH, "ais_bench/benchmark/configs/models/vllm_api/vllm_api_chat_temp.py")
    )
    # 生成 aisbench 命令
    if test_accuracy:
        ais_bench_cmd = "ais_bench --models vllm_api_chat_temp --datasets gsm8k_gen_0_shot_cot_str_perf --dump-eval-details"
    else:
        ais_bench_cmd = f"ais_bench --models vllm_api_chat_temp --datasets gsm8k_gen_0_shot_cot_str_perf --mode perf --summarizer {DEFAULT_PERFORMANCE_TEST} --debug"
    logging.info(f"test start, use command: {ais_bench_cmd}")
    # 执行命令
    if test_times > 1:
        for test_time in range(test_times):
            logging.info(f"Execution rounds: {test_time + 1}")
            os.system(ais_bench_cmd)
            time.sleep(1)
    else:
        os.system(ais_bench_cmd)
