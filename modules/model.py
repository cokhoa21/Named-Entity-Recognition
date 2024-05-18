from modules.featrep import FeatureRep
from commons import Feature
from transformers import BertModel, BertPreTrainedModel, BertConfig
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

import torch
import torch.nn as nn


class NerModel(BertPreTrainedModel):
    def __init__(self, config, feature=None, use_lstm=False, device="cpu"):
        super(NerModel, self).__init__(config)
        self.num_labels = config.num_labels
        self.use_feature = False
        self.use_lstm = False
        self.hidden_size = config.hidden_size
        self.bert = BertModel(config)
        self.ferep = None

        if feature is not None:
            self.ferep = FeatureRep(feature, device)
            self.use_feature = True
            self.hidden_size += self.ferep.feature_dim

        if use_lstm:
            self.use_lstm = True
            self.lstm = nn.LSTM(self.hidden_size, config.hidden_size, batch_first=True, num_layers=1)
            self.hidden_size = config.hidden_size

        self.dropout = nn.Dropout(config.hidden_dropout_prob)

        self.classifier = nn.Linear(self.hidden_size, config.num_labels)

        self.init_weights()

    def forward(self, input_ids, attention_masks, token_masks, segment_ids, label_masks, feats):
        batch_size, max_len = input_ids.size()
        outputs = self.bert(input_ids=input_ids,
                            attention_mask=attention_masks,
                            token_type_ids=segment_ids)

        token_reps = outputs[0]

        if self.use_feature:
            feat_reps = self.ferep(feats)
            token_reps = torch.cat([token_reps, feat_reps], dim=-1)

        valid_token_reps = torch.zeros_like(token_reps)
        for i in range(batch_size):
            jj = -1
            for j in range(max_len):
                if token_masks[i][j].item() == 1:
                    jj += 1
                    valid_token_reps[i][jj] = token_reps[i][j]

        if self.use_lstm:
            token_reps = self.dropout(valid_token_reps)
            lstm_outs, _ = self.lstm(token_reps)
            valid_token_reps = lstm_outs

        sequence_output = self.dropout(valid_token_reps)

        logits = self.classifier(sequence_output)
        mask = label_masks.view(-1) == 1
        active_logits = logits.view(-1, self.num_labels)[mask]
        return active_logits

    def calculate_loss(self, input_ids, attention_masks, token_masks, segment_ids, label_ids, label_masks, feats):
        batch_size, max_len = input_ids.size()
        outputs = self.bert(input_ids=input_ids,
                            attention_mask=attention_masks,
                            token_type_ids=segment_ids)

        token_reps = outputs[0]

        if self.use_feature:
            feat_reps = self.ferep(feats)
            token_reps = torch.cat([token_reps, feat_reps], dim=-1)

        valid_token_reps = torch.zeros_like(token_reps)
        for i in range(batch_size):
            jj = -1
            for j in range(max_len):
                if token_masks[i][j].item() == 1:
                    jj += 1
                    valid_token_reps[i][jj] = token_reps[i][j]

        if self.use_lstm:
            token_reps = self.dropout(valid_token_reps)
            lstm_outs, _ = self.lstm(token_reps)
            valid_token_reps = lstm_outs

        sequence_output = self.dropout(valid_token_reps)

        logits = self.classifier(sequence_output)
        loss_function = nn.CrossEntropyLoss()

        mask = label_masks.view(-1) == 1
        active_logits = logits.view(-1, self.num_labels)[mask]
        active_labels = label_ids.view(-1)[mask]
        loss = loss_function(active_logits, active_labels)

        return loss, (active_logits, active_labels)


def model_builder(model_name_or_path: str,
                  num_labels: int,
                  feat_config_path: str = None,
                  one_hot_embed: bool = True,
                  use_lstm= False,
                  device: torch.device = torch.device("cpu")):
    feature = None
    if feat_config_path is not None:
        feature = Feature(feat_config_path, one_hot_embed)
    config = BertConfig.from_pretrained(model_name_or_path, num_labels=num_labels)
    model = NerModel.from_pretrained(model_name_or_path, config=config, feature=feature, use_lstm=use_lstm, device=device)
    return config, model, feature


def model_builder_from_pretrained(model_name_or_path,
                                  num_labels,
                                  pre_train_path,
                                  feat_dir: str = None,
                                  one_hot_embed: bool = True,
                                  use_lstm=False,
                                  device: torch.device = torch.device("cpu")):
    feature = None
    if feat_dir is not None:
        feature = Feature(feat_dir + "/feature_config.json", one_hot_embed)
    config = BertConfig.from_pretrained(model_name_or_path, num_labels=num_labels)
    model = NerModel.from_pretrained(model_name_or_path, config=config, feature=feature, use_lstm= False, device=device)
    model.load_state_dict(torch.load(pre_train_path + "/vner_model.bin", map_location='cpu'))
    model.eval()
    return config, model, feature

if __name__ == "__main__":
    config, model, feature = model_builder(model_name_or_path="bert-base-multilingual-uncased",
                                           num_labels=21,
                                           feat_config_path="resources/feature_config.json")