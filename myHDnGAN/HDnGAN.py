from os import listdir
from os.path import join
import random
import matplotlib.pyplot as plt

import numpy as np
import os
import time
from PIL import Image
import torch
import torch.nn as nn
from torch.utils.data import Dataset
from torch.utils.data import DataLoader
import torchvision.transforms as transforms
from torchvision.transforms.functional import to_pil_image
import datetime
import tensorflow as tf
from torch.utils.tensorboard import SummaryWriter
from tensorflow.keras.layers import Conv2D, Activation, BatchNormalization, LeakyReLU, Add, Dense, Flatten, \
    UpSampling2D, PReLU
import glob
import os
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from tensorflow.keras.applications import VGG19
from tensorflow.keras.callbacks import TensorBoard
from tensorflow.keras.layers import Conv2D, Activation, BatchNormalization, LeakyReLU, Add, Dense, Flatten, \
    UpSampling2D, PReLU
import itertools
from IPython import display
import datetime
import time

#device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


# Costum dataset 생성
class MriDataset(Dataset):
    def __init__(self, path2img, direction='b2a', transform=False):
        super().__init__()
        self.direction = direction
        self.path2a = join(path2img, 'a')
        self.path2b = join(path2img, 'b')
        self.img_filenames = [x for x in listdir(self.path2a)]
        # self.transform = transform

    def __getitem__(self, index):
        a = np.load(join(self.path2a, self.img_filenames[index]))
        a = a.astype('float32')
        a = torch.from_numpy(a)
        a = a.unsqueeze(0)
        a = np.repeat(a[..., np.newaxis], 3, axis=0)
        a = a.squeeze()

        b = np.load(join(self.path2b, self.img_filenames[index]))
        b = b.astype('float32')
        b = torch.from_numpy(b)
        b = b.unsqueeze(0)
        b = np.repeat(b[..., np.newaxis], 3, axis=0)
        b = b.squeeze()

        # if self.transform:
        # a = self.transform(a)
        # b = self.transform(b)

        if self.direction == 'b2a':
            return b, a
        else:
            return a, b

    def __len__(self):
        return len(self.img_filenames)


# 데이터셋 불러오기
path2img = '/home/milab/LJH/NYH/myHDnGAN/dataset2/train'
path2img_test = '/home/milab/LJH/NYH/myHDnGAN/dataset2/test'
train_ds = MriDataset(path2img)
train_ds_test = MriDataset(path2img_test)

# 데이터 로더 생성하기
train_dl = DataLoader(train_ds, batch_size=4, shuffle=False)
train_dl_test = DataLoader(train_ds_test, batch_size=1, shuffle=False)

# UNet
class UNetDown(nn.Module):
    def __init__(self, in_channels, out_channels, normalize=True, dropout=0.0):
        super().__init__()

        layers = [nn.Conv2d(in_channels, out_channels,4, stride=2, padding=1, bias=False)]

        if normalize:
            layers.append(nn.InstanceNorm2d(out_channels)),

        layers.append(nn.LeakyReLU(0.2))

        if dropout:
            layers.append(nn.Dropout(dropout))

        self.down = nn.Sequential(*layers)

    def forward(self, x):
        x = self.down(x)
        return x

# check
x = torch.randn(16, 3, 256,256)
model = UNetDown(3,64)
down_out = model(x)
print(down_out.shape)

class UNetUp(nn.Module):
    def __init__(self, in_channels, out_channels, dropout=0.0):
        super().__init__()

        layers = [
            nn.ConvTranspose2d(in_channels, out_channels,4,2,1,bias=False),
            nn.InstanceNorm2d(out_channels),
            nn.LeakyReLU()
        ]

        if dropout:
            layers.append(nn.Dropout(dropout))

        self.up = nn.Sequential(*layers)

    def forward(self,x,skip):
        x = self.up(x)
        x = torch.cat((x,skip),1)
        return x

# check
x = torch.randn(16, 128, 64, 64)
model = UNetUp(128,64)
out = model(x,down_out)
print(out.shape)

# generator: 가짜 이미지를 생성합니다.
class GeneratorUNet(nn.Module):
    def __init__(self, in_channels=3, out_channels=3):
        super().__init__()

        self.down1 = UNetDown(in_channels, 64, normalize=False)
        self.down2 = UNetDown(64,128)
        self.down3 = UNetDown(128,256)
        self.down4 = UNetDown(256,512,dropout=0.5)
        self.down5 = UNetDown(512,512,dropout=0.5)
        self.down6 = UNetDown(512,512,dropout=0.5)
        self.down7 = UNetDown(512,512,dropout=0.5)
        self.down8 = UNetDown(512,512,normalize=False,dropout=0.5)

        self.up1 = UNetUp(512,512,dropout=0.5)
        self.up2 = UNetUp(1024,512,dropout=0.5)
        self.up3 = UNetUp(1024,512,dropout=0.5)
        self.up4 = UNetUp(1024,512,dropout=0.5)
        self.up5 = UNetUp(1024,256)
        self.up6 = UNetUp(512,128)
        self.up7 = UNetUp(256,64)
        self.up8 = nn.Sequential(
            nn.ConvTranspose2d(128,3,4,stride=2,padding=1),
            nn.Tanh()
        )

    def forward(self, x):
        d1 = self.down1(x)
        d2 = self.down2(d1)
        d3 = self.down3(d2)
        d4 = self.down4(d3)
        d5 = self.down5(d4)
        d6 = self.down6(d5)
        d7 = self.down7(d6)
        d8 = self.down8(d7)

        u1 = self.up1(d8,d7)
        u2 = self.up2(u1,d6)
        u3 = self.up3(u2,d5)
        u4 = self.up4(u3,d4)
        u5 = self.up5(u4,d3)
        u6 = self.up6(u5,d2)
        u7 = self.up7(u6,d1)
        u8 = self.up8(u7)

        return u8


from torch import nn


class ConvBlock(nn.Module):

    def __init__(self, in_channels, out_channels, stride):
        super().__init__()
        alpha = 0.2

        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride)
        self.bn = nn.BatchNorm2d(out_channels)
        self.lrelu = nn.LeakyReLU(alpha)

    def forward(self, x):
        result = self.conv(x)
        result = self.bn(result)
        return self.lrelu(result)


class Flatten(nn.Module):

    def __init__(self):
        super().__init__()

    def forward(self, x):
        return x.view(x.shape[0], -1)


class Discriminator(nn.Module):

    def __init__(self, final_feature_map_size):
        super().__init__()
        alpha = 0.2
        assert final_feature_map_size > 0

        self.input_block = nn.Sequential(
            nn.Conv2d(3, 64, kernel_size=3, stride=1),
            nn.LeakyReLU(alpha)
        )

        self.blocks = nn.Sequential(
            ConvBlock(64, 64, 2),
            ConvBlock(64, 128, 1),
            ConvBlock(128, 128, 2),
            ConvBlock(128, 256, 1),
            ConvBlock(256, 256, 2),
            ConvBlock(256, 512, 1),
            ConvBlock(512, 512, 2),
        )

        img_size = final_feature_map_size
        dense_block_input_size = 512 * img_size * img_size

        self.output_block = nn.Sequential(
            nn.AdaptiveAvgPool2d(img_size),
            Flatten(),
            nn.Linear(dense_block_input_size, 1024),
            nn.LeakyReLU(alpha),
            nn.Linear(1024, 1)
        )

    def forward(self, x):
        assert x.shape[2] >= 64 and x.shape[3] >= 64
        return self.output_block(self.blocks(self.input_block(x)))


from torch import nn
from torchvision import models


class PerceptualLoss(nn.Module):

    def __init__(self):
        super().__init__()
        model = models.vgg19(pretrained=True)
        model.eval()

        fifth_conv_layer_index = 26
        features = model.features
        self.feature_map_extractor = nn.Sequential(*list(model.features)[:fifth_conv_layer_index + 1])
        self.feature_map_extractor.eval()
        for param in self.feature_map_extractor.parameters():
            param.requires_grad = False

        self.mse = nn.L1Loss()

    def forward(self, real_image, generated_image):
        assert real_image.shape == generated_image.shape

        loss = self.mse(self.feature_map_extractor(generated_image), self.feature_map_extractor(real_image))

        return loss


class GeneratorLoss(nn.Module):

    def __init__(self):
        super().__init__()
        self.perceptual_loss = PerceptualLoss()
        self.discrimenator_loss = nn.BCEWithLogitsLoss()
        self.image_loss = nn.MSELoss()
        self.image_loss2 = nn.L1Loss()

    def forward(self, real_imges, generated_images, output_labels, target_labels):
        self.perc_loss = self.perceptual_loss(real_imges, generated_images)
        self.adv_loss = self.discrimenator_loss(output_labels, target_labels)
        self.img_loss = self.image_loss(generated_images, real_imges)
        self.img_loss2 = self.image_loss2(generated_images, real_imges)

        #return self.img_loss + self.perc_loss + 0.001 * self.adv_loss
        return self.img_loss2 + 0.001 * self.adv_loss

from torch import nn


class DiscriminatorLoss(nn.Module):

    def __init__(self):
        super().__init__()
        self.loss_critrion = nn.BCEWithLogitsLoss()

    def forward(self, output_labels, target_labels):
        return self.loss_critrion(output_labels, target_labels)


def save_state():
    import datetime
    import os

    state = {
        'epoch': epoch,
        'discriminator_state_dict': D.state_dict(),
        'generator_state_dict': G.state_dict(),
        'training_results': training_results,
        'DISCRIMINATOR_FINAL_FEATURE_MAP_SIZE': DISCRIMINATOR_FINAL_FEATURE_MAP_SIZE,
        'RESIDUAL_BLOCKS': RESIDUAL_BLOCKS

    }

    file_name = 'model ' + str(datetime.datetime.now()) + '.pth'
    file_path = os.path.join('/home/milab/LJH/NYH/myHDnGAN/Models', file_name)
    torch.save(state, file_path)
    return file_path


def load_state(file_name):
    import os
    import torch

    saved_file_src = '/home/milab/LJH/NYH/myHDnGAN/Models'
    file_path = os.path.join(saved_file_src, file_name)
    if os.path.isfile(file_path):
        return torch.load(file_path)
    else:
        return None

# Network Parameter
###############################
BATCH_SIZE = 4
EPOCH_NUM = 50
###############################
# Discriminator
###############################
DISCRIMINATOR_FINAL_FEATURE_MAP_SIZE = 10
###############################
RESIDUAL_BLOCKS = 16
# Optimizers
###############################
lr = 0.001

import torch.optim as optim

D = Discriminator(DISCRIMINATOR_FINAL_FEATURE_MAP_SIZE)
G = GeneratorUNet()


D_loss = DiscriminatorLoss()
G_loss = GeneratorLoss()


# Create optimizers for the discriminator and generator
d_optimizer = optim.SGD(D.parameters(), lr)
g_optimizer = optim.Adam(G.parameters(), lr)

###############################
# Load training state if exists
###############################
file_name = 'model 2021-08-16.pth'
state = load_state(file_name)

old_state_exists = state is not None

if old_state_exists:
  print('loading old state from', file_name)
  G.load_state_dict(state['generator_state_dict'])
  D.load_state_dict(state['discriminator_state_dict'])
else:
  print("starting from the beginning")


#D, G = D.cuda(), G.cuda()
#D_loss, G_loss = D_loss.cuda(), G_loss.cuda()

import random

# Training
INTERLEAV_TRAINING_LIMIT = -1
# For logging the losses
EPOCH_LOG_INTERVAL = 1
BATCH_LOG_INTERVAL = 5
SAVE_MODEL_INTERVAL = 2

sigmoid = nn.Sigmoid()

loss_hist = {'gen': [],
             'dis': []}

G_LOSS = "G_LOSS"
G_ADV_LOSS = "G_ADV_LOSS"
G_PERC_LOSS = "G_PERC_LOSS"
G_IMG_LOSS = "G_IMG_LOSS"
G_TRAINING_ITERATIONS = "G_TRAINING_ITERATIONS"
D_REAL_LOSS = "D_REAL_LOSS"
D_FAKE_LOSS = "D_FAKE_LOSS"
D_REAL_TRAINING_ITERATIONS = "D_REAL_TRAINING_ITERATIONS"
D_FAKE_TRAINING_ITERATIONS = "D_FAKE_TRAINING_ITERATIONS"
D_CORRECT_PREDICTIONS = "D_CORRECT_PREDICTIONS"
CURRENT_TRAINED_IMAGES = "CURRENT_TRAINED_IMAGES"
D_ACC = "D_ACC"

if old_state_exists:
    training_results = state['training_results']
    START_EPOCH = state['epoch']
else:
    training_results = {
        G_LOSS: [], G_ADV_LOSS: [], G_PERC_LOSS: [], G_IMG_LOSS: [], G_TRAINING_ITERATIONS: [],
        D_REAL_LOSS: [], D_FAKE_LOSS: [], D_REAL_TRAINING_ITERATIONS: [], D_FAKE_TRAINING_ITERATIONS: [],
        D_ACC: []
    }
    START_EPOCH = 1

train_on_fake = True

for epoch in range(START_EPOCH, EPOCH_NUM):

    running_results = {
        G_LOSS: 0, G_ADV_LOSS: 0, G_PERC_LOSS: 0, G_IMG_LOSS: 0, G_TRAINING_ITERATIONS: 0,
        D_REAL_LOSS: 0, D_FAKE_LOSS: 0, D_REAL_TRAINING_ITERATIONS: 0, D_FAKE_TRAINING_ITERATIONS: 0,
        D_CORRECT_PREDICTIONS: 0,
        CURRENT_TRAINED_IMAGES: 0
    }

    D.train()
    G.train()

    for batch_id, (a, b) in enumerate(train_dl):

        #b, a = b.cuda(), a.cuda()

        ###############################
        # Choose which netwrok to train
        ###############################

        assert running_results[D_CORRECT_PREDICTIONS] <= running_results[CURRENT_TRAINED_IMAGES]

        try:
            acc = running_results[D_CORRECT_PREDICTIONS] / running_results[CURRENT_TRAINED_IMAGES]
        except:
            acc = 0.5

        g_train = acc > 0.3
        d_train = acc < 0.85

        ###############################
        # Train the Generator
        ###############################

        if g_train:
            g_optimizer.zero_grad()

            generated_image = G(a)
            D_fake_output = D(generated_image)
            # with torch.no_grad():
            # generated_image2=np.repeat(generated_image[..., np.newaxis], 3,axis=1)
            # generated_image2=generated_image2.squeeze()
            # b2=np.repeat(b[..., np.newaxis], 3,axis=1)
            # b2=b2.squeeze()

            # The target is to make the discriminator belive that all the images are real
            g_loss = G_loss(b, generated_image, D_fake_output, torch.ones_like(D_fake_output) * 0.9)

            g_loss.backward()
            g_optimizer.step()

            running_results[G_LOSS] += g_loss.item() * BATCH_SIZE
            running_results[G_ADV_LOSS] += G_loss.adv_loss.item() * BATCH_SIZE
            running_results[G_PERC_LOSS] += G_loss.perc_loss.item() * BATCH_SIZE
            running_results[G_IMG_LOSS] += G_loss.img_loss.item() * BATCH_SIZE
            running_results[G_TRAINING_ITERATIONS] += 1
            running_results[CURRENT_TRAINED_IMAGES] += BATCH_SIZE
            running_results[D_CORRECT_PREDICTIONS] += (sigmoid(D_fake_output).cpu().detach().numpy() <= 0.5).sum()

        ###############################
        # Train the discriminator
        ###############################

        if d_train:

            d_optimizer.zero_grad()
            # If random number > 0.5 train on fake data else train on real

            if train_on_fake:
                generated_image = G(a)
                D_fake_output = D(generated_image.detach())
                # The goal is to make the discriminator get the fake images right with smooth factor
                target = torch.zeros_like(D_fake_output) + 0.1
                d_fake_loss = D_loss(D_fake_output, target)
                d_fake_loss.backward()

                running_results[D_FAKE_LOSS] += d_fake_loss.item() * BATCH_SIZE
                running_results[D_FAKE_TRAINING_ITERATIONS] += 1
                running_results[D_CORRECT_PREDICTIONS] += (sigmoid(D_fake_output).cpu().detach().numpy() <= 0.5).sum()
            else:
                D_real_output = D(b)
                # The goal is to make the discriminator get the real images right with smooth factor
                target = torch.ones_like(D_real_output) * 0.9
                d_real_loss = D_loss(D_real_output, target)
                d_real_loss.backward()

                running_results[D_REAL_LOSS] += d_real_loss.item() * BATCH_SIZE
                running_results[D_REAL_TRAINING_ITERATIONS] += 1
                running_results[D_CORRECT_PREDICTIONS] += (sigmoid(D_real_output).cpu().detach().numpy() > 0.5).sum()

            train_on_fake = not train_on_fake
            d_optimizer.step()
            running_results[CURRENT_TRAINED_IMAGES] += BATCH_SIZE

        ###############################
        # Logging
        ###############################

        total_d_iterations = running_results[D_REAL_TRAINING_ITERATIONS] + running_results[D_FAKE_TRAINING_ITERATIONS]
        total_d_loss = running_results[D_REAL_LOSS] + running_results[D_FAKE_LOSS]

        g_images = running_results[G_TRAINING_ITERATIONS] * BATCH_SIZE + 1
        d_real_images = running_results[D_REAL_TRAINING_ITERATIONS] * BATCH_SIZE + 1
        d_fake_images = (running_results[D_FAKE_TRAINING_ITERATIONS] * BATCH_SIZE + 1)



        if batch_id % BATCH_LOG_INTERVAL == 0:
            print(
                '[%d/%d/%d] Acc_D: %.4f Corr_D :%d Used_IMG_D: %d Loss_D: %.4f R_Loss_D: %.4f F_Loss_D: %.4f Loss_G: %.4f Adv_G: %.4f Perc_G: %.4f Img_G: %.4f D_Train: %d G_Train: %d' % (
                    batch_id,
                    epoch,
                    EPOCH_NUM,

                    acc,
                    running_results[D_CORRECT_PREDICTIONS],
                    running_results[CURRENT_TRAINED_IMAGES],

                    total_d_loss / (total_d_iterations * BATCH_SIZE),
                    running_results[D_REAL_LOSS] / d_real_images,
                    running_results[D_FAKE_LOSS] / d_fake_images,

                    running_results[G_LOSS] / g_images,
                    running_results[G_ADV_LOSS] / g_images,
                    running_results[G_PERC_LOSS] / g_images,
                    running_results[G_IMG_LOSS] / g_images,

                    total_d_iterations,
                    running_results[G_TRAINING_ITERATIONS]
                ))

    if epoch % EPOCH_LOG_INTERVAL == 0:
        g_images = running_results[G_TRAINING_ITERATIONS] * BATCH_SIZE + 1
        d_real_images = running_results[D_REAL_TRAINING_ITERATIONS] * BATCH_SIZE + 1
        d_fake_images = (running_results[D_FAKE_TRAINING_ITERATIONS] * BATCH_SIZE + 1)

        training_results[G_LOSS].append(running_results[G_LOSS] / g_images)
        training_results[G_ADV_LOSS].append(running_results[G_ADV_LOSS] / g_images)
        training_results[G_PERC_LOSS].append(running_results[G_PERC_LOSS] / g_images)
        training_results[G_IMG_LOSS].append(running_results[G_IMG_LOSS] / g_images)
        training_results[G_TRAINING_ITERATIONS].append(running_results[G_TRAINING_ITERATIONS])
        training_results[D_REAL_LOSS].append(running_results[D_REAL_LOSS] / d_real_images)
        training_results[D_FAKE_LOSS].append(running_results[D_FAKE_LOSS] / d_fake_images)
        training_results[D_REAL_TRAINING_ITERATIONS].append(running_results[D_REAL_TRAINING_ITERATIONS])
        training_results[D_FAKE_TRAINING_ITERATIONS].append(running_results[D_FAKE_TRAINING_ITERATIONS])
        training_results[D_ACC].append(
            running_results[D_CORRECT_PREDICTIONS] / running_results[CURRENT_TRAINED_IMAGES] + 1)

    if epoch % SAVE_MODEL_INTERVAL == 0:
        print("saving model state", save_state())

import os
import math




EPOCH_MSE = 'EPOCH_MSE'
EPOCH_SSIM = 'EPOCH_SSIM'

valing_results = {EPOCH_MSE: 0}
dataset_size = len(train_dl_test.dataset)
j = 0
dir_save = "/home/milab/LJH/NYH/myHDnGAN/results"
for batch_id, (a, b) in enumerate(train_dl_test):
    #a = a.cuda()
    #b = b.cuda()

    SR = G(a)

    valing_results[EPOCH_MSE] += ((SR - b) ** 2).data.mean() * BATCH_SIZE

    total_mse_loss = valing_results[EPOCH_MSE] / dataset_size
    psnr = 10 * math.log10(1 / total_mse_loss)

    print("MSE: %.4f  PSNR: %.4f" % (total_mse_loss, psnr))

    with torch.no_grad():
        j = j + 1
        orig_imgs = a.detach().cpu()
        fake_imgs = SR.detach().cpu()
        real_imgs = b.detach().cpu()
        np.save(os.path.join(dir_save, 'wave_%03d.npy' % j), orig_imgs.squeeze(0))
        np.save(os.path.join(dir_save, 'grappa_%03d.npy' % j), real_imgs.squeeze(0))
        np.save(os.path.join(dir_save, 'hdngan_%03d.npy' % j), fake_imgs.squeeze(0))
        # break