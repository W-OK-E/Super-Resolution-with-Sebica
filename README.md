# Super-Resolution-with-Sebica
Training the lightweight model Sebica on X-Ray Images to test the application of Super Resolution Models in Medical Imaging
## The trained model Sebica50.pth is present in the logs/ckpts/ folder, to test the model:
- Step one: Clone the Repo
- Step two: Change the path to the trained model in the file infer.py 
- Step three: Create a folder called dataset/test and put the test images in the folder
- Step 4: Run the model via the command: python3 infer.py
## Test Results
The model was trained on 2000 HR and the corresponding LR counterparts, tried to achieve a upscaling factor of 4x, the results:

/home/summer/Super-Resolution/Super-Resolution-with-Sebica/out_images/111.jpeg
