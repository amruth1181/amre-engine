"""
Model Exporter: Skywork-o1-Open-PRM-Qwen-2.5-1.5B -> ONNX INT8
Run this script on a machine with a GPU (e.g. Google Colab) to generate the ONNX artifacts,
then upload them to your Hugging Face model repository.
"""
import os
import sys

def main():
    print("🚀 Initializing PRM ONNX Exporter...")
    
    # 1. Install optimum if missing
    try:
        import optimum
        import onnxruntime
    except ImportError:
        print("📦 Installing required optimum and ONNX libraries...")
        os.system("pip install optimum[onnxruntime-gpu] transformers huggingface_hub")
        
    from optimum.onnxruntime import ORTQuantizer, ORTModelForCausalLM
    from optimum.onnxruntime.configuration import AutoQuantizationConfig
    from huggingface_hub import HfApi
    
    model_id = "Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B"
    export_dir = "./skywork-prm-onnx"
    quant_dir = "./skywork-prm-onnx-int8"
    
    # 2. Export base model to ONNX
    print(f"📥 Exporting base model '{model_id}' to ONNX (this may take a few minutes)...")
    exit_code = os.system(f"optimum-cli export onnx --model {model_id} --task causal-lm-with-past {export_dir}")
    if exit_code != 0:
        print("❌ Optimum CLI export failed. Please check your RAM/GPU availability.")
        sys.exit(1)
        
    # 3. Apply Dynamic Quantization (INT8)
    print("⚡ Quantizing ONNX model to INT8 (dynamic quantization)...")
    try:
        quantizer = ORTQuantizer.from_pretrained(export_dir, file_name="model.onnx")
        qconfig = AutoQuantizationConfig.avx2(is_static=False) # dynamic quantization optimized for x86/ARM CPUs
        quantizer.quantize(save_dir=quant_dir, quantization_config=qconfig)
        print(f"✅ Model successfully quantized and saved to: {quant_dir}")
    except Exception as e:
        print(f"❌ Quantization failed: {e}")
        sys.exit(1)
        
    # 4. Copy tokenizer configuration files
    print("copying tokenizer and config files...")
    os.system(f"cp {export_dir}/tokenizer* {quant_dir}/ 2>/dev/null || true")
    os.system(f"cp {export_dir}/special_tokens_map.json {quant_dir}/ 2>/dev/null || true")
    os.system(f"cp {export_dir}/vocab.json {quant_dir}/ 2>/dev/null || true")
    os.system(f"cp {export_dir}/merges.txt {quant_dir}/ 2>/dev/null || true")
    os.system(f"cp {export_dir}/config.json {quant_dir}/ 2>/dev/null || true")
    
    print("\n🎉 Export completed successfully!")
    print(f"The quantized files are located in '{quant_dir}' folder.")
    print("\n👉 To upload this folder to your Hugging Face Hub, run:")
    print("==========================================================")
    print("from huggingface_hub import HfApi")
    print("api = HfApi()")
    print("api.create_repo(repo_id='YOUR_HF_USERNAME/skywork-prm-1.5b-onnx-int8', repo_type='model', exist_ok=True)")
    print("api.upload_folder(folder_path='./skywork-prm-onnx-int8', repo_id='YOUR_HF_USERNAME/skywork-prm-1.5b-onnx-int8', repo_type='model')")
    print("==========================================================")

if __name__ == "__main__":
    main()
